# PyCode Studio — publicação web no Render

Esta pasta contém a versão web adaptada para abrir em navegador, com senha de acesso. O professor não precisa instalar o programa no computador dele.

## Publicar
1. Envie **todos** os arquivos desta pasta para um repositório GitHub (na raiz do repositório).
2. No Render, abra Dashboard → New + → Blueprint.
3. Selecione o repositório e confirme a configuração encontrada em `render.yaml`.
4. Aguarde o serviço ficar `Live`. O Render fornece uma URL `https://...onrender.com`.
5. No painel do serviço, abra Environment e defina `PYCODE_ACCESS_PASSWORD` com uma senha longa que você compartilhe apenas com seu professor. Configure `GEMINI_API_KEY` com uma chave do Google AI Studio. O Tutor utiliza o plano gratuito quando disponível; limites e períodos de alta demanda podem causar respostas HTTP 429 ou 503. O aplicativo não faz várias tentativas automáticas em sequência.

## O que esta adaptação faz
- O servidor escuta na porta `PORT` do Render.
- Exige login para API de execução, testes e tutor.
- O cookie de sessão é protegido e HTTPS é exigido na publicação.
- O processo de Python executado não recebe as variáveis de ambiente da aplicação, para não expor a chave da IA diretamente via `os.environ`.
- O Tutor usa `google-genai` e as variáveis `GEMINI_API_KEY` e `GEMINI_MODEL`; não depende de `OPENAI_API_KEY`.
- O workspace é temporário: atualizar a página preserva os arquivos na mesma sessão; reiniciar o serviço limpa o workspace e inicia um projeto limpo.

## Limitação importante de segurança
Esta é uma versão para demonstração controlada, não uma sandbox de execução de código multiusuário. O código Python enviado pode ter permissões de leitura/escrita do contêiner. Não publique para uso geral nem compartilhe a senha publicamente. Para uma turma inteira ou acesso público, execute cada programa em um contêiner isolado com limites de CPU/memória, sistema de arquivos restrito e sem segredos acessíveis.

## Uso local
`iniciar.bat` continua disponível para execução local no Windows. A autenticação web exige `PYCODE_ACCESS_PASSWORD`; para uso local, defina uma senha antes de iniciar ou use a versão original local.
