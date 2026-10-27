# flag-service (Python)

Este é o serviço de CRUD (Create, Read, Update, Delete) do projeto ToggleMaster. Ele é responsável por gerenciar as *definições* das feature flags.

**IMPORTANTE:** Este serviço é protegido e depende que o `auth-service` esteja rodando. Todas as requisições (exceto `/health`) exigem um header `Authorization: Bearer <sua-chave-api>`.

## 📦 Pré-requisitos (Local)

* [Python](https://www.python.org/) (versão 3.9 ou superior)
* [PostgreSQL](https://www.postgresql.org/download/) (rodando localmente ou em um contêiner Docker)
*  Docker e Docker Compose
* O `auth-service` deve estar rodando (localmente na porta `8001`).
* Acesso ao GitHub Actions e ao repositório GitOps do projeto

## 📂 Estrutura do projeto

- `app.py`: aplicação Flask com autenticação, CRUD e conexão ao PostgreSQL
- `db/init.sql`: script de criação da tabela `flags`
- `Dockerfile`: imagem de container do serviço
- `docker-compose.yaml`: ambiente local com PostgreSQL e serviço da aplicação
- `k8s/`: manifests Kubernetes para deploy e configuração
- `.github/workflows/ci-flag.yaml`: pipeline CI/CD do serviço
- `test_app.py`: testes automatizados da API

## <img src="https://raw.githubusercontent.com/marwin1991/profile-technology-icons/refs/heads/main/icons/docker.png" width="25" height="25" /> Execução com Docker Compose

O arquivo [docker-compose.yaml](docker-compose.yaml) já configura:

- contêiner do PostgreSQL
- contêiner do `flag-service`
- rede compartilhada com outros microserviços

Para subir o ambiente:

```bash
docker compose up --build
```

O serviço ficará acessível em:

- http://localhost:8002

## <img src="https://raw.githubusercontent.com/marwin1991/profile-technology-icons/refs/heads/main/icons/postgresql.png" width="25" height="25" /> Banco de dados

A tabela principal é `flags`, criada pelo script [db/init.sql](db/init.sql):

- `id`: identificador
- `name`: nome único da flag
- `description`: descrição da funcionalidade
- `is_enabled`: flag ativa/inativa
- `created_at`: timestamp de criação
- `updated_at`: timestamp de atualização

Além disso, há um trigger para atualizar automaticamente `updated_at` em cada `UPDATE`.

## <img src="https://raw.githubusercontent.com/marwin1991/profile-technology-icons/refs/heads/main/icons/kubernetes.png" width="25" height="25" /> Kubernetes e deploy

A pasta [k8s](k8s) contém os manifests do deploy em cluster Kubernetes, incluindo:

- `flag-service-deployment.yaml`: deployment com 2 réplicas
- `flag-service-service.yaml`: serviço do app
- `flag-service-config.yaml`: ConfigMap com variáveis do serviço
- `flag-service-secret.yaml`: segredos da aplicação
- `postgres-deployment.yaml`: banco PostgreSQL
- `postgres-service.yaml`: serviço do banco
- `postgres-pvc.yaml`: persistência do volume
- `postgres-init-configmap.yaml`: configuração inicial do banco
- `rds-init-job.yaml`: job para provisionamento/bootstrapping do RDS
- `kustomization.yaml`: orquestração dos manifests

Observações importantes:

- O deployment do `flag-service` expõe a porta `8002`
- Há probes de liveness e readiness em `/health`
- O serviço usa `DATABASE_URL` e `AUTH_SERVICE_URL` configurados via env
- O namespace utilizado é `toggle-master`

## CI/CD no AWS Academy

O pipeline da branch produtiva `aws-cloud-k8s` autentica com o repository secret
`AWS_ACADEMY_CREDENTIALS`. Cole o bloco de **AWS Details → AWS CLI**, com
`aws_access_key_id`, `aws_secret_access_key` e `aws_session_token`.
O cabeçalho `[default]` é opcional. O secret é configurado neste repositório;
o secret do auth-service não é compartilhado automaticamente.

O workflow usa `ramondata/CI-reusable-source`, fixado por SHA, no modo Academy.
As credenciais são validadas e mascaradas, sem assumir uma role via OIDC.
O código-fonte e a imagem passam pelas verificações antes da publicação no ECR.
Pull requests executam somente as verificações, sem autenticar na AWS.

| Variável opcional | Valor padrão |
| --- | --- |
| `AWS_REGION` | `us-east-1` |
| `ECR_REPOSITORY` | `toggle-master/flag-service` |
| `APP_VERSION` | `v1.0.0` |

O ECR deve existir na conta e região do laboratório. A tag publicada segue
`APP_VERSION-SHA_CURTO`, por exemplo `v1.0.0-abcdef1`.

A cada reinício do laboratório, substitua o bloco inteiro do secret e use
**Re-run all jobs** numa execução por push que já contenha esta alteração.
Alterar o secret não dispara o pipeline. O botão **Run workflow** depende de
este arquivo também existir na branch padrão do repositório.

### GitOps automático

Após a publicação da imagem, o pipeline atualiza automaticamente o repositório
existente `ramondata/toggle-master-gitops`. Configure `GITOPS_DEPLOY_KEY` neste
repositório com uma chave privada autorizada a escrever no GitOps.
Os pushes fazem rebase e até três tentativas para acomodar atualizações de
outros serviços na mesma branch sem usar force push.
O job atualiza repositório e tag em `apps/flag-service/values.yaml`, na
`master`. A configuração de ArgoCD e do cluster é uma etapa separada.

## 🚀 Rodando Localmente

1.  **Clone o repositório** e entre na pasta `flag-service`.

2.  **Prepare o Banco de Dados:**
    * Crie um banco de dados no seu PostgreSQL (ex: `flags_db`).
    * Execute o script `db/init.sql` para criar a tabela `flags`:
        ```bash
        psql -U seu_usuario -d flags_db -f db/init.sql
        ```

3.  **Configure as Variáveis de Ambiente:**
    Crie um arquivo chamado `.env` na raiz desta pasta (`flag-service/`) com o seguinte conteúdo:
    ```.env
    # String de conexão do seu banco de dados PostgreSQL
    DATABASE_URL="postgres://SEU_USUARIO:SUA_SENHA@localhost:5432/flags_db"
    
    # Porta que este serviço (flag-service) irá rodar
    PORT="8002"
    
    # URL do auth-service (que deve estar rodando na porta 8001)
    AUTH_SERVICE_URL="http://localhost:8001"
    ```

4.  **Instale as Dependências:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Inicie o Serviço:**
    ```bash
    gunicorn --bind 0.0.0.0:8002 app:app
    ```
    O servidor estará rodando em `http://localhost:8002`.

## 🧪 Testando os Endpoints

**Primeiro, você precisa de uma chave de API válida!**

1.  Vá até o terminal do `auth-service` (que deve estar rodando) e crie uma chave:
    ```bash
    curl -X POST http://localhost:8001/admin/keys \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer admin-secreto-123" \
    -d '{"name": "admin-para-flag-service"}'
    ```
2.  Copie a chave retornada (ex: `tm_key_...`). Vamos chamá-la de `SUA_CHAVE_API` no resto dos exemplos.

---

**Agora, teste o `flag-service`:**

**1. Verifique a Saúde (Health Check):**
```bash
curl http://localhost:8002/health
```

Saída esperada: `{"status":"ok"}`

**2. Tente Acessar um Endpoint Protegido (Sem Chave):**
```bash
curl http://localhost:8002/flags
```

Saída esperada: `{"error":"Authorization header obrigatório"}`

**3. Crie uma nova Flag (Com a Chave Correta):**
```bash
curl -X POST http://localhost:8002/flags \
-H "Content-Type: application/json" \
-H "Authorization: Bearer SUA_CHAVE_API" \
-d '{
    "name": "enable-new-dashboard",
    "description": "Ativa o novo dashboard para usuários",
    "is_enabled": true
}'
```
Saída esperada: (Um JSON com os dados da flag criada).

**4. Liste todas as Flags:**
```bash
curl http://localhost:8002/flags \
-H "Authorization: Bearer SUA_CHAVE_API"
```
Saída esperada: (Uma lista `[]` contendo a flag que você criou).

**5. Desative a Flag (PUT):**
```bash
curl -X PUT http://localhost:8002/flags/enable-new-dashboard \
-H "Content-Type: application/json" \
-H "Authorization: Bearer SUA_CHAVE_API" \
-d '{"is_enabled": false}'
```
Saída esperada: (O JSON da flag atualizada, com `"is_enabled": false`).

[def]: https://shields.io
