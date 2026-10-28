# PyCode Studio — aplicativo local

Esta versão usa a interface existente do PyCode Studio, mas adiciona um backend Python local para que o código seja executado pelo Python instalado no computador, em vez de depender apenas do interpretador limitado do navegador.

## Requisitos

- Windows 10/11 recomendado (também é possível iniciar manualmente em outros sistemas).
- Python 3.10 ou superior instalado e disponível como `py -3` ou `python`.
- Internet para instalar as dependências e carregar os recursos visuais externos do editor. O interpretador local funciona sem mandar o código para um serviço remoto.

## Início rápido no Windows

1. Extraia toda a pasta do ZIP para um local em que você tenha permissão de gravação.
2. Dê dois cliques em `iniciar.bat`.
3. Na primeira execução, o programa cria um ambiente Python isolado e instala as dependências.
4. O PyCode Studio abrirá em `http://127.0.0.1:8765`. Mantenha a janela preta aberta enquanto usa o aplicativo.

### Janela de aplicativo desktop (opcional)

Execute `iniciar_desktop.bat`. Isso instala `pywebview` e tenta abrir uma janela própria. Se a janela nativa não funcionar no seu Windows, use `iniciar.bat`, que abre a versão local no navegador.

## O que foi adicionado

- Execução pelo Python real instalado no computador, com imports dos pacotes instalados nesse ambiente.
- Terminal com entrada interativa para `input()`: digite no campo de entrada e pressione Enter/Enviar.
- Arquivos virtuais do projeto são gravados no diretório `workspace/project` antes da execução; arquivos criados pelo código permanecem nessa pasta.
- Verificação de sintaxe sem executar o programa.
- Testes automatizados do backend, acessíveis pelo botão **Testes** no editor ou por `python -m unittest discover -s tests -v`.
- Tutor de IA para explicação linha a linha, depuração e perguntas.
- Execução por voz com terminal próprio e entrada para `input()`.
- Endpoints locais acessíveis somente pelo endereço de loopback configurado no iniciador.

## Ativar o Tutor de IA

O tutor fica desativado até que uma chave válida seja configurada. Abra `.env` (criado na primeira inicialização) e preencha `OPENAI_API_KEY` com uma chave fornecida pelo responsável/administrador da conta. O modelo padrão é `gpt-5.5`; ele pode ser alterado por `OPENAI_MODEL` se a conta não tiver acesso a esse modelo.

**Privacidade e custos:** quando você clica em um botão do tutor, a pergunta e, se a caixa estiver marcada, o código e o último erro são enviados ao provedor de IA para gerar a resposta. A API pode gerar custos conforme a conta e o uso. Nunca coloque a chave de API no HTML, no GitHub ou em capturas de tela. Sem chave, a IDE e o Python local continuam funcionando.

## Arquivos

- `index.html` — interface.
- `app.py` — servidor local, execução Python, tutor e verificações.
- `desktop.py` — inicializador opcional da janela desktop.
- `workspace/project/` — arquivos de trabalho e arquivos gerados pelos programas.
- `tests/` — testes automatizados do backend.
- `.env.example` — modelo de configuração, sem segredo.

## Limites honestos

- O editor Monaco e alguns estilos são carregados de CDNs, portanto a primeira abertura precisa de internet para esses recursos.
- Os pacotes Python que podem ser importados são os instalados no Python selecionado para executar `app.py`. Para instalar um pacote, use o mesmo Python/ambiente virtual da aplicação.
- O código executado tem as permissões do usuário atual do computador. Execute apenas código que você entende ou confia; o backend local não é um ambiente de sandbox seguro para executar código desconhecido.
- O tutor de IA é opcional e exige acesso à API. Não existe uma IA ilimitada ou gratuita embutida no programa.
- Esta é uma versão de desenvolvimento testada por verificações automatizadas e de sintaxe, não uma garantia de ausência de todos os bugs em qualquer computador.
