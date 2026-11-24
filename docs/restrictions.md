# Azure for Students restrictions encountered

| Restriction hit | Error message | Solution applied |
|-----------------|---------------|------------------|
| Imposed regions (5 allowed) | Policy limits deployment to indiasouthcentral, uaenorth, eastasia, indonesiacentral, koreacentral | Intersected with the Flex Consumption list (indiasouthcentral drops out), then tested Cosmos DB capacity first: koreacentral accepted it, so it became the single project region |
| az provider register timeout | Connection to management.azure.com timed out | Re-checked state with az provider list, re-registered; all providers Registered |
