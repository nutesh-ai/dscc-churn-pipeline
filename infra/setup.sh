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
