# PyCode Studio — versão online (Render)

O PyCode Studio é acessado diretamente pelo endereço HTTPS do serviço no Render. **Não é necessário executar `iniciar.bat`, instalar Python ou abrir uma janela desktop.**

## Publicação no Render

1. Envie os arquivos e a pasta `tests/` deste projeto para a raiz do repositório GitHub.
2. No Render, escolha **New → Blueprint** e selecione o repositório que contém `render.yaml`.
3. Confirme a criação do serviço `pycode-studio` e aguarde o estado `Live`.
4. No serviço, abra **Environment** e configure `GEMINI_API_KEY` com a chave criada no Google AI Studio. Não coloque essa chave no HTML nem no GitHub.
5. Confira `GEMINI_MODEL`. O padrão definido no Blueprint é `gemini-3.8-flash`. A disponibilidade do modelo e os limites gratuitos são controlados pelo Google e podem variar.
6. Confira `PYCODE_ACCESS_PASSWORD`. O Blueprint gera uma senha; você pode definir uma senha própria e compartilhá-la apenas com quem deve acessar o editor.
7. Abra a URL HTTPS `https://...onrender.com`. O acesso é feito pelo navegador.

O `render.yaml` configura automaticamente `PYCODE_SESSION_SECRET` e `PYCODE_HTTPS_ONLY`.

## Recursos da versão online

- Editor Monaco no navegador.
- Execução Python no servidor do PyCode Studio, com terminal e suporte a `input()`.
- Verificação de sintaxe Python pelo backend.
- Tutor IA usando Gemini, com explicação, depuração e perguntas.
- Criação de arquivos e pastas com caminhos como `funcoes/calculos.py`.
- Abas de arquivos e árvore de pastas expansível.
- Baixar o arquivo atual, importar arquivos de texto/código e exportar/importar o projeto completo em JSON.
- Arquivos mantidos durante a sessão atual do navegador e recuperados ao atualizar a página, enquanto a mesma instância do servidor continuar ativa.

## Como salvar e transportar projetos

- **Baixar arquivo atual:** baixa o arquivo selecionado para o computador.
- **Exportar projeto completo:** baixa um JSON com todos os arquivos e caminhos de pastas.
- **Importar projeto:** selecione um JSON exportado pelo PyCode Studio para restaurar o conjunto de arquivos.
- O navegador mantém uma cópia temporária em `sessionStorage`, vinculada ao identificador de inicialização do servidor.

### Atenção ao armazenamento no Render

Este Blueprint usa o plano gratuito do Render. O sistema de arquivos do serviço é temporário: arquivos escritos pelo backend podem desaparecer quando o serviço reinicia, entra em suspensão ou recebe um novo deploy. Por isso, os projetos de trabalho ficam guardados no navegador e devem ser exportados em JSON como backup.

A cópia do navegador não sincroniza automaticamente entre computadores. Para ter um projeto centralizado e persistente, compartilhado entre seu computador e o do professor, será necessário adicionar um banco de dados ou armazenamento persistente compatível com o plano do serviço. Não considere a pasta temporária do servidor como backup.

## Segurança

- A chave `GEMINI_API_KEY` fica somente nas variáveis de ambiente do servidor e não é enviada ao processo que executa os programas Python.
- O acesso às rotas de execução, testes e tutor exige login.
- O backend limita o tamanho dos arquivos e do projeto e encerra execuções após 120 segundos.
- **Importante:** executar código Python enviado pelo navegador não é uma sandbox de segurança. O código executado tem permissões do processo do servidor. Mantenha o acesso restrito a pessoas de confiança; não publique a IDE para execução pública ou irrestrita.

## Arquivos do repositório

- `app.py` — servidor FastAPI, autenticação, execução Python e integração Gemini.
- `index.html` — interface web.
- `requirements.txt` — dependências do serviço.
- `render.yaml` — configuração de publicação no Render.
- `tests/test_backend.py` — testes automatizados do backend.

A versão online não depende de `desktop.py`, `requirements-desktop.txt`, `iniciar.bat` ou `iniciar_desktop.bat`.
