#!/usr/bin/env bash
# Azure foundation for the churn pipeline. Run step by step, not as one script.
# Windows/MSYS2 only: stop bash from rewriting /fileName into a Windows path
export MSYS2_ARG_CONV_EXCL="*"

EQ=nutesh
LOC=koreacentral          # allowed region + Flex Consumption + Cosmos capacity OK
RG=rg-projet-$EQ
COSMOS=cosmos-$EQ

# Providers (once per subscription)
for p in Microsoft.Web Microsoft.App Microsoft.EventGrid Microsoft.DocumentDB \
         Microsoft.OperationalInsights Microsoft.Insights Microsoft.ManagedIdentity; do
  az provider register --namespace $p; done

# Resource group with mandatory tags
az group create -n $RG -l $LOC --tags projet=dscc equipe=$EQ

# Cosmos DB first: it is the service most often refused for capacity
az cosmosdb create -n $COSMOS -g $RG --enable-free-tier true \
  --locations regionName=$LOC failoverPriority=0 isZoneRedundant=False \
  --tags projet=dscc equipe=$EQ
az cosmosdb sql database create -a $COSMOS -g $RG -n pipeline --throughput 400
az cosmosdb sql container create -a $COSMOS -g $RG -d pipeline -n inferences \
  --partition-key-path "/fileName"

# Budget ($25, alerts at 20/50/80%) was created in the portal: Cost Management > Budgets

# Monitoring FIRST: workspace capped at 0.2 GB/day + workspace-based App Insights, both in the RG
LAW=log-$EQ; AI=appi-$EQ
az monitor log-analytics workspace create -g $RG -n $LAW -l $LOC --quota 0.2 --tags projet=dscc equipe=$EQ
LAW_ID=$(az monitor log-analytics workspace show -g $RG -n $LAW --query id -o tsv)
az monitor app-insights component create --app $AI -g $RG -l $LOC --workspace $LAW_ID --tags projet=dscc equipe=$EQ

# Storage: containers, queue, static website, versioning
ST=st${EQ}pipe
az storage account create -n $ST -g $RG -l $LOC --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 --allow-blob-public-access false --tags projet=dscc equipe=$EQ
az storage account blob-service-properties update --account-name $ST -g $RG --enable-versioning true
for c in input output rejected models; do az storage container create --account-name $ST -n $c; done
az storage queue create --account-name $ST -n inference-requests
az storage blob service-properties update --account-name $ST --static-website --index-document index.html

# Container Apps: ONE environment, logs to the capped workspace; placeholder image until the API is built
ENV=cae-$EQ
az containerapp env create -n $ENV -g $RG -l $LOC \
  --logs-workspace-id $(az monitor log-analytics workspace show -g $RG -n $LAW --query customerId -o tsv) \
  --logs-workspace-key $(az monitor log-analytics workspace get-shared-keys -g $RG -n $LAW --query primarySharedKey -o tsv) \
  --tags projet=dscc equipe=$EQ
az containerapp create -n api-$EQ -g $RG --environment $ENV \
  --image mcr.microsoft.com/k8se/quickstart:latest --target-port 80 --ingress external \
  --cpu 0.25 --memory 0.5Gi --min-replicas 0 --max-replicas 2 --tags projet=dscc equipe=$EQ

# Flex Consumption Function App (Python 3.12, 512 MB)
FUNC=func-$EQ
az functionapp create -n $FUNC -g $RG --storage-account $ST --app-insights $AI \
  --flexconsumption-location $LOC --runtime python --runtime-version 3.12 \
  --instance-memory 512 --tags projet=dscc equipe=$EQ

# Identity-based connections: role assignments made ONCE by the subscription owner
az functionapp identity assign -n $FUNC -g $RG
PID=$(az functionapp identity show -n $FUNC -g $RG --query principalId -o tsv)
ST_ID=$(az storage account show -n $ST -g $RG --query id -o tsv)
for r in "Storage Blob Data Owner" "Storage Queue Data Contributor"; do
  az role assignment create --role "$r" --assignee-object-id $PID \
    --assignee-principal-type ServicePrincipal --scope $ST_ID; done
# Cosmos DB data plane (Built-in Data Contributor): not an Azure RBAC role
az cosmosdb sql role assignment create -a $COSMOS -g $RG --scope "/" \
  --principal-id $PID --role-definition-id 00000000-0000-0000-0000-000000000002

# Managed identity for GitHub Actions (OIDC): no Entra ID rights needed, Contributor on the RG only
ID=id-github-$EQ
az identity create -n $ID -g $RG -l $LOC --tags projet=dscc equipe=$EQ
az identity federated-credential create -n github-production --identity-name $ID -g $RG \
  --issuer https://token.actions.githubusercontent.com \
  --subject repo:nutesh-ai/dscc-churn-pipeline:environment:production \
  --audiences api://AzureADTokenExchange
az role assignment create --role Contributor \
  --assignee-object-id $(az identity show -n $ID -g $RG --query principalId -o tsv) \
  --assignee-principal-type ServicePrincipal --scope $(az group show -n $RG --query id -o tsv)

# Managed identity for GitHub Actions (OIDC): no Entra ID rights needed, Contributor on the RG only
ID=id-github-$EQ
az identity create -n $ID -g $RG -l $LOC --tags projet=dscc equipe=$EQ
az identity federated-credential create -n github-production --identity-name $ID -g $RG \
  --issuer https://token.actions.githubusercontent.com \
  --subject repo:nutesh-ai/dscc-churn-pipeline:environment:production \
  --audiences api://AzureADTokenExchange
az role assignment create --role Contributor \
  --assignee-object-id $(az identity show -n $ID -g $RG --query principalId -o tsv) \
  --assignee-principal-type ServicePrincipal --scope $(az group show -n $RG --query id -o tsv)
