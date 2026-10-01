# Referência visual do chefe (2026-10-01)

`referencia_dashboard_chefe_2026-10-01.png`: mockup enviado pelo chefe como alvo de aparência ("quero algo bonito, igual a foto").
Classificação: FORJA_RULE de direção visual. Não é tela pronta.

O que vale: tema escuro grafite com acento cobre; sidebar com grupos; header com seletor de equipamento, ONLINE e selo Somente leitura;
bloco "O que o sistema está vendo" com chip de condição; 6 indicadores (Setpoint, Vazão, Drive Command, RPM, Belt Load, Canal INT) com
mini-tendência; linha do tempo de eventos; cards da visão da planta; painel de diagnóstico com "O que mudou", "Hipóteses" (com selo de
evidência), "O que verificar primeiro" e "Fontes"; bloco de comunicação com estado do driver.

O que NÃO entra, por regra do produto:
- "Coleta de dados do CLP": PLC não é fonte. O texto correto é "leitura direta do KCM via Host/Anybus".
- Foto real da máquina: entra um desenho técnico animado do dosador (SVG) que reage a RPM e Belt Load (spec §38–41).
- Linguagem de causa no diagnóstico ("caracterizando baixa alimentação"): fica "comportamento compatível com", com nível de evidência.
- Protocolo como botão escolhido (Modbus TCP marcado): só o simulador está disponível; os outros mostram "Não suportado / Disponível na fase J/K".
- Usuário/planta no header ("Planta Principal"): planta vem do perfil (GTEX — PHA); login só na fase M.
