# Linguagem Cuco

| Dados acadêmicos |
|---|
| Universidade Federal do Tocantins (UFT) |
| Compiladores |
| Profa. Dra. Anna Paula Rodrigues |
| Luís Gustavo Alves Bezerra e Heitor Fernandes Carrijo |
||

A Cuco é uma linguagem de programação baseada em C, criada para simplificar o uso de estruturas de dados. Ela estende a sintaxe de C com listas (List), filas (Queue) e pilhas (Stack) nativas. Programas escritos em Cuco são transpilados para C17 e podem ser compilados com o GCC.

O transpilador da Cuco transforma um arquivo `.cuco` em código C equivalente por meio de quatro etapas:

1. **Análise léxica.** O *lexer* lê o código-fonte e o divide em tokens, como identificadores, números e operadores.
2. **Análise sintática.** O *parser* verifica se os tokens seguem a gramática da linguagem e constrói a árvore sintática abstrata (AST).
3. **Análise semântica.** O analisador verifica declarações, tipos e chamadas de métodos. Por exemplo, ele identifica se o método chamado pertence à estrutura e se os argumentos são compatíveis.
4. **Geração de código.** A partir da AST anotada, o gerador produz um arquivo `.c` com o código equivalente e as funções de suporte às estruturas utilizadas.

O **GCC** compila o arquivo `.c` gerado e produz o executável.

### Cuco - Comandos de execução

python3 -m venv .venv    
source .venv/bin/activate

| Etapa | Comando | Resultado |
|---|---|---|
| Instalar dependências | `python -m pip install -r requirements.txt` | Instala o `pycparser`. |
| Preparar a pasta de saídas | `mkdir -p outputs` | Cria a pasta para os arquivos gerados. |
| Lexer | `python main.py lexer examples/stack.cuco` | Mostra os tokens no terminal. |
| Lexer em JSON | `python main.py lexer examples/stack.cuco -o outputs/stack.tokens.json` | Salva os tokens. |
| Parser | `python main.py parser examples/stack.cuco` | Mostra a árvore sintática (AST) em JSON. |
| Parser em JSON | `python main.py parser examples/stack.cuco -o outputs/stack.ast.json` | Salva a AST. |
| Análise semântica | `python main.py semantic examples/stack.cuco` | Valida o programa e mostra a AST anotada e a tabela de símbolos. |
| Semântico em JSON | `python main.py semantic examples/stack.cuco -o outputs/stack.semantic.json` | Salva a saída semântica. |
| Gerar C | `python main.py build examples/stack.cuco -o outputs/stack.c` | Transpila o programa para C17. |
| Compilar C | `gcc -std=c17 -Wall -Wextra outputs/stack.c -o outputs/stack` | Gera o executável. |
| Executar | `./outputs/stack` | Roda o programa compilado. |
| Fluxo completo com Make | `make` | Transpila, compila e roda o exemplo de pilha. |
| Fluxo completo com arquivo .cuco     | `make run SOURCE=examples/meu_teste.cuco` | Transpila, compila e roda o arquivo indicado. |
| Compilar com Make | `make build SOURCE=examples/meu_teste.cuco` | Gera o C e o executável em `outputs/`. |

Nos comandos do Makefile, passe `CC=gcc` para selecionar o GCC explicitamente.

### Declaração das estruturas

Na Cuco, os nomes usados no código são `List`, `Stack` e `Queue`. O tipo do elemento vem entre `< >` após o nome da estrutura. Para definir um limite fixo, coloque a capacidade entre `< >` após o identificador.

| Estrutura | Capacidade dinâmica | Capacidade fixa |
|---|---|---|
| **Lista** | `List<int> lista;` | `List<int> lista<10>;` |
| **Pilha** | `Stack<int> pilha;` | `Stack<int> pilha<10>;` |
| **Fila** | `Queue<int> fila;` | `Queue<int> fila<10>;` |

- **Capacidade dinâmica.** A estrutura começa com espaço para 8 elementos e pode crescer quando fica cheia.
- **Capacidade fixa.** A estrutura mantém o limite definido na declaração. Se ficar cheia, a próxima tentativa de inserção retorna `false`.
- **Tipo opcional.** Se você omitir o tipo, a Cuco usa `int`. Por exemplo, `Stack pilha;` equivale a `Stack<int> pilha;`.
- **Limite por variável.** A capacidade fixa pode ser um literal inteiro positivo ou uma variável inteira. O valor é lido no momento da declaração.

```c
int limite = 10;

Stack<float> notas<limite>;
notas.push(8.5f);

float topo = notas.peek();

free(notas);
```


### Tabela de estruturas e funções disponíveis

#### Lista (`List`)

Use uma lista quando precisar acessar, inserir ou remover elementos por posição. O primeiro elemento fica no índice `0`.

| Método | Uso | Retorno |
|---|---|---|
| `add(valor)` | Adiciona um elemento ao final da lista. | `true` se inseriu, `false` se a inserção falhou. |
| `insert(índice, valor)` | Insere um elemento na posição indicada e desloca os seguintes. | `true` se inseriu, `false` se a inserção falhou. |
| `get(índice)` | Consulta o elemento na posição indicada. | Elemento consultado. |
| `set(índice, valor)` | Substitui o elemento na posição indicada. | `void` |
| `remove(índice)` | Remove o elemento na posição indicada e desloca os seguintes. | Elemento removido. |

#### Pilha (`Stack`)

Use uma pilha quando o último elemento inserido deve ser o primeiro a sair (LIFO). Um exemplo é o histórico de ações para desfazer.

| Método | Uso | Retorno |
|---|---|---|
| `push(valor)` | Insere um elemento no topo. | `true` se inseriu, `false` se a inserção falhou. |
| `pop()` | Remove o elemento do topo. | Elemento removido. |
| `peek()` | Consulta o elemento do topo sem removê-lo. | Elemento consultado. |

#### Fila (`Queue`)

Use uma fila quando o primeiro elemento inserido deve ser o primeiro a sair (FIFO). Um exemplo é uma fila de atendimento.

| Método | Uso | Retorno |
|---|---|---|
| `enqueue(valor)` | Insere um elemento no final da fila. | `true` se inseriu, `false` se a inserção falhou. |
| `dequeue()` | Remove o primeiro elemento da fila. | Elemento removido. |
| `peek()` | Consulta o primeiro elemento da fila sem removê-lo. | Elemento consultado. |

#### Operações comuns às três estruturas

| Operação | Uso | Retorno |
|---|---|---|
| `size()` | Informa quantos elementos estão armazenados. | `size_t` |
| `capacity()` | Informa a capacidade atual da estrutura. | `size_t` |
| `isEmpty()` | Verifica se a estrutura está vazia. | `true` ou `false`. |
| `isFull()` | Verifica se a capacidade atual foi atingida. Estruturas dinâmicas ainda podem crescer na próxima inserção. | `true` ou `false`. |
| `clear()` | Esvazia a estrutura e mantém a capacidade alocada. | `void` |
| `free(estrutura)` | Libera a memória da estrutura. É uma chamada de função. | `void` |

Uma inserção retorna `false` quando a estrutura tem capacidade fixa e está cheia, ou quando a expansão de uma estrutura dinâmica falha. Índices inválidos e chamadas a `pop()`, `dequeue()` ou `peek()` em uma estrutura vazia geram erro de execução.