from __future__ import annotations

import asyncio
import hmac
import re
import secrets
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
WORKSPACE_ROOT = BASE_DIR / "workspace" / "users"
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="PyCode Studio", version="2.1.0")
# A senha e a chave de sessão devem ser configuradas como variáveis de ambiente no Render.
# Valores de desenvolvimento permitem rodar localmente, mas não devem ser usados em produção.
SESSION_SECRET = os.getenv("PYCODE_SESSION_SECRET", "local-dev-secret-change-before-deploy")
ACCESS_PASSWORD = os.getenv("PYCODE_ACCESS_PASSWORD", "")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.getenv("PYCODE_HTTPS_ONLY", "false").lower() == "true",
    max_age=60 * 60 * 12,
)
RUN_LOCK = asyncio.Lock()
MAX_FILE_BYTES = 2_000_000
MAX_PROJECT_BYTES = 10_000_000


class CodeRequest(BaseModel):
    code: str = Field(default="", max_length=500_000)


class LoginRequest(BaseModel):
    password: str = Field(default="", max_length=300)


class TutorRequest(BaseModel):
    mode: str = Field(default="question", max_length=30)
    question: str = Field(default="", max_length=8_000)
    code: str = Field(default="", max_length=100_000)
    error: str = Field(default="", max_length=8_000)


def safe_filename(name: str) -> str:
    """Return a single safe filename; never accept a path from the client."""
    cleaned = str(name or "main.py").replace("\\", "/").split("/")[-1].strip()
    cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in "._- ")
    if not cleaned or cleaned in {".", ".."}:
        return "main.py"
    if len(cleaned) > 120:
        stem, dot, suffix = cleaned.rpartition(".")
        cleaned = (stem[:100] + dot + suffix[:12]) if dot else cleaned[:120]
    return cleaned


def build_tutor_prompt(mode: str, question: str, code: str, error: str) -> str:
    mode_instructions = {
        "explain": (
            "Explique o código linha por linha para um estudante iniciante. "
            "Defina os conceitos e mostre a sequência de execução."
        ),
        "debug": (
            "Investigue os erros do código. Identifique o trecho relevante, "
            "explique a causa provável e apresente uma correção."
        ),
        "question": (
            "Responda naturalmente à mensagem do estudante. "
            "Se for uma saudação ou conversa casual, converse normalmente. "
            "Se for uma dúvida de Python, explique de forma simples. "
            "Faça perguntas para esclarecer mensagens confusas."
        ),
    }

    task = mode_instructions.get(mode, mode_instructions["question"])
    parts = [task]

    if question.strip():
        parts.append("Mensagem do estudante:\n" + question.strip())

    # Só envia o código quando o modo pede explicação ou depuração.
    if mode in ("explain", "debug") and code.strip():
        parts.append(
            "Código Python:\n```python\n"
            + code[:100_000]
            + "\n```"
        )

    if mode in ("explain", "debug") and error.strip():
        parts.append(
            "Último erro capturado:\n" + error.strip()[:8_000]
        )

    parts.append(
        "Responda em português do Brasil, com linguagem acessível "
        "a iniciantes. Não afirme que executou um código se não executou. "
        "Não invente resultados. Prefira correções pequenas e explique "
        "o motivo das alterações."
    )

    return "\n\n".join(parts)

def write_project_files(files: Any, current_filename: str, current_code: str) -> Path:
    if not isinstance(files, dict):
        files = {}
    total = 0
    written: set[str] = set()
    for raw_name, raw_content in files.items():
        if not isinstance(raw_content, str):
            continue
        name = safe_filename(str(raw_name))
        content = raw_content.encode("utf-8")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError(f"O arquivo {name} excede o limite de 2 MB.")
        total += len(content)
        if total > MAX_PROJECT_BYTES:
            raise ValueError("O projeto excede o limite de 10 MB.")
        (WORKSPACE_DIR / name).write_bytes(content)
        written.add(name)
    main_name = safe_filename(current_filename)
    code_bytes = current_code.encode("utf-8")
    if len(code_bytes) > MAX_FILE_BYTES:
        raise ValueError("O código atual excede o limite de 2 MB.")
    (WORKSPACE_DIR / main_name).write_bytes(code_bytes)
    return WORKSPACE_DIR / main_name


@app.get("/")
def home() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.post("/api/login")
def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
    configured = os.getenv("PYCODE_ACCESS_PASSWORD", "").strip()
    # Facilita o uso local sem configuração; o Render sempre recebe a variável pelo Blueprint.
    if not configured and os.getenv("RENDER", "").lower() != "true":
        configured = "pycode-local"
    if not configured:
        raise HTTPException(status_code=503, detail="O acesso ainda não foi configurado pelo administrador.")
    if not hmac.compare_digest(payload.password, configured):
        raise HTTPException(status_code=401, detail="Senha incorreta. Tente novamente.")
    request.session.clear()
    request.session["authenticated"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request) -> dict[str, Any]:
    request.session.clear()
    return {"ok": True}


def require_login(request: Request) -> None:
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Faça login para usar o PyCode Studio.")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "pythonVersion": sys.version.split()[0],
        "aiConfigured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
    }


@app.post("/api/check")
def check_syntax(payload: CodeRequest, _auth: None = Depends(require_login)) -> dict[str, Any]:
    try:
        compile(payload.code, "<editor>", "exec")
        return {"ok": True, "message": "Sintaxe Python válida."}
    except SyntaxError as exc:
        return {
            "ok": False,
            "error": f"SyntaxError na linha {exc.lineno}, coluna {exc.offset}: {exc.msg}",
            "line": exc.lineno,
            "column": exc.offset,
        }



@app.post("/api/tutor")
async def tutor(payload: TutorRequest, _auth: None = Depends(require_login)) -> dict[str, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="A chave GEMINI_API_KEY não está configurada no Render."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="A biblioteca google-genai não está instalada. Confira o requirements.txt."
        ) from exc

    prompt = build_tutor_prompt(
        payload.mode,
        payload.question,
        payload.code,
        payload.error,
    )

    def call_model() -> str:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Você é o Tutor PyCode Studio, um professor de Python "
                    "paciente e preciso. Responda em português do Brasil, "
                    "com linguagem acessível a iniciantes. Use títulos curtos, "
                    "exemplos pequenos e blocos de código quando necessário. "
                    "Seja honesto sobre incertezas. Nunca solicite senhas "
                    "ou chaves de API."
                ),
                max_output_tokens=1800,
            ),
        )

        answer = response.text
        if not answer:
            raise ValueError("O Gemini retornou uma resposta vazia.")

        return answer

    try:
        answer = await asyncio.to_thread(call_model)
        return {"answer": answer}
    except Exception as exc:
        print(f"Erro na API Gemini: {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(
            status_code=502,
            detail=(
                "O Gemini não conseguiu responder. "
                "Consulte os logs do servidor para identificar a causa. "
                f"Erro: {type(exc).__name__}"
            ),
        ) from exc




@app.post("/api/tests")
def run_tests(_auth: None = Depends(require_login)) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        return {"ok": result.returncode == 0, "returncode": result.returncode, "output": output or "Nenhum teste foi encontrado."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": 124, "output": "Os testes excederam o limite de 40 segundos."}


@app.websocket("/ws/run")
async def run_python(websocket: WebSocket) -> None:
    # Conexões remotas só podem usar o terminal após autenticação por cookie de sessão.
    if not websocket.scope.get("session", {}).get("authenticated"):
        await websocket.close(code=1008, reason="Faça login para usar o PyCode Studio.")
        return
    origin = websocket.headers.get("origin", "")
    if origin:
        parsed_origin = urlsplit(origin)
        request_host = websocket.headers.get("host", "")
        # Bloqueia origens externas diferentes do próprio site (proteção contra CSWSH).
        if parsed_origin.netloc != request_host:
            await websocket.close(code=1008, reason="Origem não autorizada.")
            return
    await websocket.accept()
    process: asyncio.subprocess.Process | None = None
    try:
        request = await websocket.receive_json()
        if request.get("type") != "run":
            await websocket.send_json({"type": "error", "text": "Mensagem inicial inválida."})
            await websocket.close()
            return
        code = str(request.get("code", ""))
        filename = safe_filename(request.get("filename", "main.py"))
        try:
            script_path = write_project_files(request.get("files", {}), filename, code)
        except (ValueError, OSError) as exc:
            await websocket.send_json({"type": "error", "text": str(exc)})
            await websocket.close()
            return

        async with RUN_LOCK:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                str(script_path),
                cwd=str(WORKSPACE_DIR),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                # Não repassa chaves de API/segredos do servidor ao programa executado.
                env={
                    "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUNBUFFERED": "1",
                    "HOME": str(WORKSPACE_DIR),
                    "TMPDIR": str(WORKSPACE_DIR),
                },
            )
            await websocket.send_json({"type": "started", "python": sys.version.split()[0]})

            async def forward_output() -> None:
                assert process is not None and process.stdout is not None
                while True:
                    chunk = await process.stdout.read(1024)
                    if not chunk:
                        break
                    await websocket.send_json({"type": "output", "text": chunk.decode("utf-8", errors="replace")})
                return_code = await process.wait()
                await websocket.send_json({"type": "exit", "code": return_code})

            async def receive_input() -> None:
                assert process is not None and process.stdin is not None
                while True:
                    message = await websocket.receive_json()
                    kind = message.get("type")
                    if kind == "input":
                        text = str(message.get("text", ""))[:20_000]
                        process.stdin.write(text.encode("utf-8", errors="replace"))
                        await process.stdin.drain()
                    elif kind == "stop":
                        if process.returncode is None:
                            process.terminate()
                        return

            output_task = asyncio.create_task(forward_output())
            input_task = asyncio.create_task(receive_input())
            timeout_task = asyncio.create_task(asyncio.sleep(120))
            done, pending = await asyncio.wait({output_task, input_task, timeout_task}, return_when=asyncio.FIRST_COMPLETED)
            if timeout_task in done:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3)
                    except asyncio.TimeoutError:
                        process.kill()
                await websocket.send_json({"type": "error", "text": "Execução interrompida após 120 segundos para evitar que um programa fique preso."})
            elif input_task in done and output_task not in done:
                if process.returncode is None:
                    process.terminate()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if task is not timeout_task and task.exception():
                    raise task.exception()  # type: ignore[misc]
    except WebSocketDisconnect:
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "text": f"Falha ao executar o Python: {type(exc).__name__}: {exc}"})
        except Exception:
            pass
        if process and process.returncode is None:
            process.terminate()
    finally:
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    # Render fornece PORT; localmente, o iniciador continua usando a porta 8765.
    host = os.getenv("PYCODE_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", os.getenv("PYCODE_PORT", "8765")))
    uvicorn.run(app, host=host, port=port, log_level="warning")
