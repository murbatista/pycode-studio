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
load_dotenv(BASE_DIR / ".env")
INDEX_FILE = BASE_DIR / "index.html"
WORKSPACE_ROOT = Path(os.getenv("PYCODE_DATA_DIR", str(BASE_DIR / "workspace" / "users"))).expanduser()
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PyCode Studio", version="2.1.0")
# A senha e a chave de sessão devem ser configuradas como variáveis de ambiente no Render.
# Valores de desenvolvimento permitem rodar localmente, mas não devem ser usados em produção.
SESSION_SECRET = os.getenv("PYCODE_SESSION_SECRET", "local-dev-secret-change-before-deploy")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.getenv("PYCODE_HTTPS_ONLY", "false").lower() == "true",
    max_age=60 * 60 * 12,
)
WORKSPACE_LOCKS: dict[str, asyncio.Lock] = {}

def get_workspace_lock(workspace_id: str) -> asyncio.Lock:
    """Evita concorrência no mesmo projeto sem bloquear outros usuários."""
    lock = WORKSPACE_LOCKS.get(workspace_id)
    if lock is None:
        lock = asyncio.Lock()
        WORKSPACE_LOCKS[workspace_id] = lock
    return lock
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
    """Converte um caminho informado em um caminho relativo seguro do projeto."""
    cleaned = str(name or "main.py").replace("\\", "/").strip()
    if re.match(r"^[A-Za-z]:/", cleaned) or cleaned.startswith("/"):
        cleaned = cleaned.rsplit("/", 1)[-1]
    raw_parts = cleaned.split("/")

    if len(raw_parts) > 10:
        raise ValueError("Caminho de arquivo inválido.")

    # Remove segmentos de navegação e mantém o destino dentro do projeto.
    parts = [part.strip() for part in raw_parts if part.strip() not in {"", ".", ".."}]
    if not parts:
        return "main.py"

    safe_parts = []
    for part in parts:
        part = "".join(ch for ch in part if ch.isalnum() or ch in "._- ")
        if not part or part in {".", ".."}:
            continue
        if len(part) > 120:
            raise ValueError("Nome de arquivo muito longo.")
        safe_parts.append(part)

    return "/".join(safe_parts) if safe_parts else "main.py"

def get_session_workspace(session: dict[str, Any]) -> Path:
    workspace_id = session.get("workspace_id")

    if not isinstance(workspace_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{40,64}", workspace_id
    ):
        workspace_id = secrets.token_urlsafe(32)
        session["workspace_id"] = workspace_id

    root = WORKSPACE_ROOT.resolve()
    workspace = (root / workspace_id).resolve()

    if root not in workspace.parents:
        raise ValueError("Pasta de projeto inválida.")

    workspace.mkdir(parents=True, exist_ok=True)

    return workspace

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

def write_project_files(
    files: Any,
    current_filename: str,
    current_code: str,
    workspace_dir: Path
) -> Path:

    if not isinstance(files, dict):
        files = {}

    workspace = workspace_dir.resolve()
    total = 0

    def get_safe_path(raw_name: str) -> Path:
        name = safe_filename(raw_name)
        destination = (workspace / name).resolve()

        if not destination.is_relative_to(workspace):
            raise ValueError("Caminho fora da pasta do projeto.")

        current = workspace

        for part in name.split("/"):
            current = current / part

            if current.is_symlink():
                raise ValueError("Links simbólicos não são permitidos.")

        return destination

    for raw_name, raw_content in files.items():
        if not isinstance(raw_content, str):
            continue

        destination = get_safe_path(str(raw_name))
        content = raw_content.encode("utf-8")

        if len(content) > MAX_FILE_BYTES:
            raise ValueError(
                f"O arquivo {raw_name} excede o limite de 2 MB."
            )

        total += len(content)

        if total > MAX_PROJECT_BYTES:
            raise ValueError("O projeto excede o limite de 10 MB.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    main_path = get_safe_path(current_filename)
    code_bytes = current_code.encode("utf-8")

    if len(code_bytes) > MAX_FILE_BYTES:
        raise ValueError("O código atual excede o limite de 2 MB.")

    main_path.parent.mkdir(parents=True, exist_ok=True)
    main_path.write_bytes(code_bytes)

    return main_path


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
    request.session["workspace_id"] = secrets.token_urlsafe(32)

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
    session = websocket.scope.get("session", {})

    if not session.get("authenticated"):
        await websocket.close(
            code=1008,
            reason="Faça login para usar o PyCode Studio."
        )
        return

    workspace_dir = get_session_workspace(session)

    origin = websocket.headers.get("origin", "")
    if origin:
        parsed_origin = urlsplit(origin)
        request_host = websocket.headers.get("host", "")

        if parsed_origin.netloc != request_host:
            await websocket.close(
                code=1008,
                reason="Origem não autorizada."
            )
            return

    await websocket.accept()

    process = None
    tasks = []

    try:
        request = await websocket.receive_json()

        if request.get("type") != "run":
            await websocket.send_json({
                "type": "error",
                "text": "Mensagem inicial inválida."
            })
            return

        
        code = str(request.get("code", ""))
        filename = safe_filename(request.get("filename", "main.py"))

        workspace_id = str(session.get("workspace_id", ""))
        workspace_lock = get_workspace_lock(workspace_id)
        async with workspace_lock:

            try:
                script_path = write_project_files(
                    request.get("files", {}),
                    filename,
                    code,
                    workspace_dir
                )
            except (ValueError, OSError) as exc:
                await websocket.send_json({
                    "type": "error",
                    "text": str(exc)
                })
                return
                

        
            runner_code = r'''
import builtins
import os
import runpy
import sys

script_path = os.path.abspath(sys.argv[1])
workspace_dir = os.getcwd()

sys.argv = [script_path]

# Permite localizar módulos em qualquer subpasta do projeto.
sys.path.insert(0, workspace_dir)

def pycode_input(prompt=""):
    if prompt:
        sys.stdout.write(str(prompt))
        sys.stdout.flush()

    sys.stdout.write("\x1ePYCODE_STUDIO_INPUT\x1e")
    sys.stdout.flush()

    line = sys.stdin.readline()

    if line == "":
        raise EOFError

    return line.rstrip("\r\n")

builtins.input = pycode_input

runpy.run_path(script_path, run_name="__main__")
'''

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                "-c",
                runner_code,
                str(script_path),
                cwd=str(workspace_dir),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={
                    "PATH": os.getenv(
                        "PATH",
                        "/usr/local/bin:/usr/bin:/bin"
                    ),
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUNBUFFERED": "1",
                    "HOME": str(workspace_dir),
                    "TMPDIR": str(workspace_dir),
                },
            )

            await websocket.send_json({
                "type": "started",
                "python": sys.version.split()[0]
            })

            input_marker = b"\x1ePYCODE_STUDIO_INPUT\x1e"

            async def forward_output():
                assert process.stdout is not None

                pending = bytearray()

                async def send_visible(data: bytes):
                    if data:
                        await websocket.send_json({
                            "type": "output",
                            "text": data.decode(
                                "utf-8",
                                errors="replace"
                            )
                        })

                while True:
                    chunk = await process.stdout.read(4096)

                    if not chunk:
                        break

                    pending.extend(chunk)

                    while True:
                        marker_position = pending.find(input_marker)

                        if marker_position < 0:
                            break

                        await send_visible(
                            bytes(pending[:marker_position])
                        )

                        await websocket.send_json({
                            "type": "input_requested"
                        })

                        del pending[
                            :marker_position + len(input_marker)
                        ]

                    keep_length = 0
                    max_keep = min(
                        len(pending),
                        len(input_marker) - 1
                    )

                    for size in range(max_keep, 0, -1):
                        if pending[-size:] == input_marker[:size]:
                            keep_length = size
                            break

                    visible_length = len(pending) - keep_length

                    if visible_length > 0:
                        await send_visible(
                            bytes(pending[:visible_length])
                        )

                        del pending[:visible_length]

                await send_visible(bytes(pending))

            async def receive_input():
                assert process.stdin is not None

                while True:
                    message = await websocket.receive_json()
                    kind = message.get("type")

                    if kind == "input":
                        text_input = str(
                            message.get("text", "")
                        )[:20_000]

                        if not text_input.endswith(("\n", "\r")):
                            text_input += "\n"

                        process.stdin.write(
                            text_input.encode(
                                "utf-8",
                                errors="replace"
                            )
                        )

                        await process.stdin.drain()

                    elif kind == "stop":
                        return

            output_task = asyncio.create_task(forward_output())
            input_task = asyncio.create_task(receive_input())
            wait_task = asyncio.create_task(process.wait())
            timeout_task = asyncio.create_task(asyncio.sleep(120))

            tasks = [
                output_task,
                input_task,
                wait_task,
                timeout_task
            ]

            done, pending = await asyncio.wait(
                {input_task, wait_task, timeout_task},
                return_when=asyncio.FIRST_COMPLETED
            )

            if timeout_task in done and process.returncode is None:
                process.terminate()

                try:
                    await asyncio.wait_for(wait_task, timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    await wait_task

                await websocket.send_json({
                    "type": "error",
                    "text": "Execução interrompida após 120 segundos."
                })

            elif input_task in done and process.returncode is None:
                process.terminate()

                try:
                    await asyncio.wait_for(wait_task, timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    await wait_task

            await output_task

            if input_task in done:
                input_error = input_task.exception()

                if input_error:
                    raise input_error

            await websocket.send_json({
                "type": "exit",
                "code": process.returncode
            })

    except WebSocketDisconnect:
        pass

    except Exception as exc:
        try:
            await websocket.send_json({
                "type": "error",
                "text": (
                    f"Falha ao executar o Python: "
                    f"{type(exc).__name__}: {exc}"
                )
            })
        except Exception:
            pass

    finally:
        if process and process.returncode is None:
            process.terminate()

            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True
            )



if __name__ == "__main__":
    import uvicorn
    # Render fornece PORT; localmente, o iniciador continua usando a porta 8765.
    host = os.getenv("PYCODE_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", os.getenv("PYCODE_PORT", "8765")))
    uvicorn.run(app, host=host, port=port, log_level="warning")
