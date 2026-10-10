# Guia da visita de campo

Roteiro para a primeira visita a um KCM real. Base: Documento Mestre §11 e §12 (`docs/derived/`), regras do produto (`CLAUDE.md`) e as telas do Forja. A Forja só lê: nenhum passo aqui envia comando ao KCM.

## 1. Antes de sair

- Pacote do Windows instalado no PC que vai ficar na planta (`packaging/LEIA-ME.txt`), com o serviço rodando e a interface abrindo em `http://127.0.0.1:8765/app`.
- Backup feito (Sistema › Backup) e conferido.
- Cadastro do equipamento (Sistema › Equipamentos) com o que já se sabe; o resto fica desconhecido.
- Imprimir a lista "O que falta levantar em campo" da Ficha técnica.

## 2. Levantar sem desconectar nada

Ordem do Documento Mestre §12.1:

1. Fotografar e identificar o hardware (CPU do KCM, MDU, SFT, SIB, encoder, motor, interface Host/Anybus), sem desconectar nada.
2. Confirmar a aplicação (WBF ou LWF) e a versão de software do KCM na tela do próprio KCM.
3. Identificar o modelo e o part number do Anybus.
4. Identificar IP, máscara, Host File e KGR.
5. Seguir o cabo de rede e desenhar a topologia (quem fala com o KCM hoje, por qual switch).

Registrar tudo na Ficha técnica e em Componentes, com a evidência de cada informação (foto da tela = observado em campo; documento da máquina = documento da máquina). RJ45 ocupado no Anybus não define o protocolo: não escolher EtherNet/IP nem Modbus por suposição.

## 3. Observação passiva ou teste ativo mínimo

| | Observação passiva | Teste ativo mínimo (Forja) |
|---|---|---|
| O que é | Olhar o tráfego que já existe entre o KCM e o sistema atual | A Forja abre uma conexão e faz só leituras |
| Envia pacote ao KCM | Não | Sim, só funções de leitura |
| Precisa de | SPAN/mirror no switch ou TAP de rede, e ferramenta de captura fora da Forja | IP, protocolo e mapping configurados em KCM › Comunicação |
| Cuidado | Porta comum do switch não garante ver tráfego unicast: não concluir "não há comunicação" por uma captura sem pacotes | Confirmar com o responsável da planta que o KCM aceita mais uma conexão de leitura |

Preferir a observação passiva quando houver dúvida sobre o protocolo. A Forja não faz varredura de rede nem descoberta automática; a captura passiva é feita com ferramenta própria da TI, fora do produto.

Nunca:
- usar divisor passivo de RJ45;
- inserir switch numa comunicação industrial que está funcionando sem planejamento e autorização;
- desconectar o cabo do sistema atual para "testar".

## 4. Configurar e testar na Forja

1. KCM › Comunicação: protocolo, endereço, porta (o botão "Usar a porta padrão do protocolo" só preenche quando clicado), tempos e o mapping (endereço, tipo, ordem dos bytes, escala) a partir do documento da máquina.
2. "Conferir configuração (sem conectar)".
3. "Testar comunicação — somente leitura": ver, por variável, onde foi lido, o valor bruto, o decodificado e a qualidade.
4. Comparar com a tela do KCM no próprio painel de teste ("Confere" / "Diverge").
5. Salvar e só então "Ativar coleta". Sem teste bem-sucedido da configuração salva, a coleta não liga — nem na partida do serviço.

## 5. Comissionamento

KCM › Comissionamento: abrir a sessão (técnico, data, protocolo encontrado, versão do KCM, Host/Anybus, IP, máscara, mapping) e registrar cada conferência valor da Forja × valor na tela do KCM (setpoint, vazão, esforço do acionamento, velocidade, material na correia e alarme, só o que o KCM expõe). Encerrar com a conclusão e guardar o relatório (CSV e impressão).

Só depois da conferência rastreável a variável deixa de ser "não validada" (`UNCERTAIN`) e passa a validada (`GOOD`).

## 6. Antes de ir embora

- Tempo Real mostrando as variáveis com qualidade validada.
- Saúde e logs sem erro de comunicação.
- Backup feito depois da configuração.
- Fotos e anotações guardadas fora do repositório (dado da planta não entra no git).
