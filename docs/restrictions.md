# Azure for Students restrictions encountered

| Restriction hit | Error message | Solution applied |
|-----------------|---------------|------------------|
| Imposed regions (5 allowed) | Policy limits deployment to indiasouthcentral, uaenorth, eastasia, indonesiacentral, koreacentral | Intersected with the Flex Consumption list (indiasouthcentral drops out), then tested Cosmos DB capacity first: koreacentral accepted it, so it became the single project region |
| az provider register timeout | Connection to management.azure.com timed out | Re-checked state with az provider list, re-registered; all providers Registered |
| MSYS2 /tmp not visible to Azure CLI (Windows) | az: /tmp/probes.yaml does not exist | Wrote the YAML to a git-ignored project folder (.local/) instead; secrets never committed |
| Static Web Apps often outside allowed regions | policy violation at creation | Dashboard hosted as a Blob static website ($web); /api/recent CORS restricted to that origin |
