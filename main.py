# main.py

import json
from datetime import datetime
from typing import AsyncGenerator, List, Optional

import httpx
import sqlmodel
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select

# --- 1. 数据库模型定义 ---
class Conversation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    messages: List["ChatMessage"] = Relationship(back_populates="conversation", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    conversation_id: Optional[int] = Field(default=None, foreign_key="conversation.id")
    conversation: Optional[Conversation] = Relationship(back_populates="messages")

# --- 2. 数据库设置 ---
DATABASE_FILE = "database.db"
engine = create_engine(f"sqlite:///{DATABASE_FILE}", connect_args={"check_same_thread": False})

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# --- 3. FastAPI 应用 ---
app = FastAPI()
OLLAMA_HOST = "http://localhost:11434"

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# --- 4. API 端点 ---
@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        with open("index.html", "r", encoding="utf-8") as f: return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>错误：找不到 index.html</h1>", status_code=404)
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)
@app.get("/api/conversations", response_model=List[Conversation])
def get_conversations():
    with Session(engine) as session:
        return session.exec(select(Conversation).order_by(Conversation.created_at.desc())).all()
@app.get("/api/conversations/{conversation_id}", response_model=List[ChatMessage])
def get_conversation_messages(conversation_id: int):
    with Session(engine) as session:
        return session.exec(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.created_at)).all()
@app.get("/api/models")
async def get_models():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
            response.raise_for_status()
            return response.json().get("models", [])
        except Exception: return []
class TitleUpdateRequest(SQLModel):
    title: str
@app.put("/api/conversations/{conversation_id}/title", response_model=Conversation)
def update_conversation_title(conversation_id: int, request: TitleUpdateRequest):
    with Session(engine) as session:
        conversation = session.get(Conversation, conversation_id)
        if not conversation: raise HTTPException(status_code=404, detail="Conversation not found")
        conversation.title = request.title
        session.add(conversation); session.commit(); session.refresh(conversation)
        return conversation
@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int):
    with Session(engine) as session:
        conversation = session.get(Conversation, conversation_id)
        if not conversation: raise HTTPException(status_code=404, detail="Conversation not found")
        session.delete(conversation); session.commit()
        return Response(status_code=204)

class ChatRequest(SQLModel):
    prompt: str
    conversation_id: Optional[int] = None
    model: str
class RegenerateRequest(SQLModel):
    message_id: int
    new_prompt: str
    model: str

async def stream_ollama_response(request: ChatRequest, conversation_id: int) -> AsyncGenerator[str, None]:
    """一个异步生成器，用于构建上下文、流式处理 Ollama 的响应并保存到数据库"""
    
    # --- 1. 构建上下文 (Context Building) ---
    messages_for_ollama = []
    
    # 简单的 Token 估算：1个 token 约等于 4 个英文字符或 1-2 个中文字符。我们用字符数除以 2.5 作为估算。
    CONTEXT_CHAR_LIMIT = 4096 * 2 # 假设 4096 tokens, 留出一半给模型生成
    current_chars = 0

    with Session(engine) as session:
        # 从数据库中获取此对话的所有历史记录，按时间倒序
        history = session.exec(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
        ).all()
        
        # 从后往前遍历历史记录，构建上下文
        for msg in history:
            msg_chars = len(msg.content)
            if current_chars + msg_chars > CONTEXT_CHAR_LIMIT:
                break # 超出预算，停止添加
            
            messages_for_ollama.append({"role": msg.role, "content": msg.content})
            current_chars += msg_chars
            
    # 因为我们是倒序添加的，所以需要反转回来，让对话顺序正确
    messages_for_ollama.reverse()
    
    print(f"--- Context for Ollama: {len(messages_for_ollama)} messages, approx {current_chars / 2.5:.0f} tokens ---")

    # --- 2. 流式请求 (Streaming Request) ---
    full_response_content = ""
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", f"{OLLAMA_HOST}/api/chat", json={
            "model": request.model,
            "messages": messages_for_ollama, 
            "stream": True
        }) as response:
            if response.status_code != 200:
                error_content = await response.aread(); yield f"data: {json.dumps({'error': f'Ollama API Error: {error_content.decode()}'})}\n\n"; return
            
            async for line in response.aiter_lines():
                if line:
                    try:
                        chunk = json.loads(line); content_piece = chunk.get("message", {}).get("content")
                        if content_piece:
                            full_response_content += content_piece; yield f"data: {json.dumps({'content': content_piece})}\n\n"
                        if chunk.get("done"):
                            with Session(engine) as session:
                                assistant_message = ChatMessage(role="assistant", content=full_response_content, conversation_id=conversation_id)
                                session.add(assistant_message); session.commit(); session.refresh(assistant_message)
                                yield f"data: {json.dumps({'done': True, 'message': assistant_message.model_dump(mode='json')})}\n\n"
                    except json.JSONDecodeError: pass

@app.post("/api/chat")
async def chat_stream(request: ChatRequest):
    with Session(engine) as session:
        if request.conversation_id is None:
            conversation = Conversation(title=request.prompt[:50]); session.add(conversation); session.commit(); session.refresh(conversation)
        else:
            conversation = session.get(Conversation, request.conversation_id)
            if not conversation: raise HTTPException(status_code=404, detail="Conversation not found")
        user_message = ChatMessage(role="user", content=request.prompt, conversation_id=conversation.id)
        session.add(user_message); session.commit(); session.refresh(user_message)
        initial_data = {"user_message": user_message.model_dump(mode='json'), "conversation_id": conversation.id}
    

    async def combined_stream():
        yield f"data: {json.dumps(initial_data)}\n\n"
        async for chunk in stream_ollama_response(request, conversation.id): yield chunk
    return StreamingResponse(combined_stream(), media_type="text/event-stream")


@app.post("/api/regenerate")
async def regenerate_from_prompt(request: RegenerateRequest):
    with Session(engine) as session:
        original_message = session.get(ChatMessage, request.message_id)
        if not original_message or original_message.role != 'user': raise HTTPException(status_code=404, detail="Original user message not found")
        conversation_id = original_message.conversation_id
        timestamp_of_edit = original_message.created_at
        
        messages_to_delete = session.exec(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).where(ChatMessage.created_at >= timestamp_of_edit)).all()
        for msg in messages_to_delete: session.delete(msg)
        
        session.commit()

        new_user_message = ChatMessage(role="user", content=request.new_prompt, conversation_id=conversation_id)
        session.add(new_user_message); session.commit(); session.refresh(new_user_message)

        chat_request_for_stream = ChatRequest(prompt=request.new_prompt, conversation_id=conversation_id, model=request.model)
        initial_data = {"user_message": new_user_message.model_dump(mode='json'), "conversation_id": conversation_id}
    
    async def combined_stream():
        yield f"data: {json.dumps(initial_data)}\n\n"
        async for chunk in stream_ollama_response(chat_request_for_stream, conversation_id): yield chunk
    return StreamingResponse(combined_stream(), media_type="text/event-stream")