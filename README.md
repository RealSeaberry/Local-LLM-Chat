# Local LLM Chat


This is a minimalist prototype of a private, web-based chat application for Large Language Models (LLMs), built with Ollama and FastAPI. It allows you to deploy a language model service on your local machine and access it securely from any device on your local network (e.g., phone, tablet).

As a **prototype**, this project is primarily intended for personal experimentation and learning. It provides a basic yet feature-complete chat experience, including:

*   **Multi-Device Access:** Seamlessly access the chat interface via a browser on your LAN.
*   **Secure by Default:** Uses Caddy to provide HTTPS encryption and password protection out of the box.
*   **Conversation Memory:** Implements a sliding context window for short-term conversation memory.
*   **Streaming Responses:** AI replies are streamed word-by-word with a typewriter effect for a better user experience.
*   **Theming:** Includes several UI themes, such as a dark mode.
*   **Full Conversation Management:** Supports creating, switching between, renaming, and deleting chat histories.

## Tech Stack

*   **Backend:** Python, FastAPI
*   **AI Service:** Ollama
*   **Web Server / Reverse Proxy:** Caddy
*   **Frontend:** Vanilla HTML, CSS, JavaScript
*   **Database:** SQLite (managed with SQLModel)

## Getting Started

Before you begin, ensure you have **Python 3.10+** and **Ollama** installed on your host machine.

### 1. Clone and Prepare the Environment

```bash
# Clone this repository
git clone https://github.com/your-username/local-llm-chat.git
cd local-llm-chat

# (Recommended) Create and activate a Conda virtual environment
conda create -n web-llm python=3.10
conda activate web-llm

# Install Python dependencies
pip install "fastapi[all]" httpx sqlmodel
```

### 2. Configure Caddy (Security Core)

This project uses [Caddy](https://caddyserver.com/) as a reverse proxy to provide HTTPS and password protection.

1.  **Download Caddy:** Download the standard binary for your OS from [Caddy's GitHub Releases page](https://github.com/caddyserver/caddy/releases/latest). Place the `caddy.exe` (or `caddy`) executable in the project's root directory.

2.  **Create Configuration File:**
    Copy the provided template to create your local configuration file.
    ```bash
    cp Caddyfile.template Caddyfile
    ```

3.  **Edit `Caddyfile`:**
    *   **Find your computer's LAN IP:** Run `ipconfig` (Windows) or `ifconfig` (macOS/Linux) in your terminal to find your IPv4 address (e.g., `192.168.1.100`).
    *   Replace all instances of the `{YOUR_LAN_IP}` placeholder in the `Caddyfile` with your actual IP address.
    *   **Generate a Password Hash (CRITICAL!):** Run the following command in your terminal, replacing `"your_super_secret_password"` with a strong password of your choice.
        ```bash
        # On Windows
        .\caddy.exe hash-password --plaintext "your_super_secret_password"

        # On macOS/Linux
        ./caddy hash-password --plaintext "your_super_secret_password"
        ```
    *   Copy the entire long hash output (starting with `JDJh...`).
    *   Replace the `{YOUR_PASSWORD_HASH}` placeholder in the `Caddyfile` with the hash you just generated. You can also change the default `admin` username if you wish.

4.  **Configure Firewall:**
    Ensure your operating system's firewall allows incoming connections on port `443`. You may need to create a new inbound rule for the Caddy executable.

### 3. Running the Services

You will need **three separate** terminal windows to run all the services.

*   **Terminal 1: Start Ollama**
    Make sure the Ollama service is running in the background.
    ```bash
    ollama serve
    ```

*   **Terminal 2: Start the FastAPI App**
    ```bash
    conda activate web-llm
    uvicorn main:app --host 127.0.0.1 --port 8000
    ```

*   **Terminal 3: Start Caddy**
    ```bash
    # On Windows
    .\caddy.exe run

    # On macOS/Linux
    ./caddy run
    ```

### 4. Accessing Your App

1.  Ensure your phone (or other device) is connected to the **same Wi-Fi network** as the host computer.
2.  Open the browser on your device and navigate to `https://{YOUR_LAN_IP}` (e.g., `https://192.168.1.100`).
3.  Your browser will show a security warning because the certificate is self-signed. This is expected. Click "Advanced" and "Proceed" to continue.
4.  An authentication prompt will appear. Enter the username and password you configured in the `Caddyfile`.
5.  Enjoy your private AI chat assistant!

## Disclaimers

*   This is a **prototype** project, intended for learning and demonstration purposes. Please do not deploy it in an untrusted production environment without further security hardening.
*   The `database.db` and `Caddyfile` are intentionally included in `.gitignore` to prevent accidentally committing your chat history and credentials.
*   All conversation data is stored locally in the `database.db` file. Please handle it with care.

## Future Possibilities

*   Integrate the `caddy-security` plugin for a more user-friendly login page.
*   Implement more sophisticated context management strategies (e.g., summarization).
*   Further refine the mobile UI/UX.

