# Proto Review: /Users/qzou/git/ef-client/protos/aidiscovery/mcp_session.proto

**Issues:** 318 (1 errors, 307 warnings, 10 info)

## !!! Type mismatch for 'models_used' field

The field 'models_used' is defined as 'repeated string' but the canonical type for 'ai_model_identifier' is 'string'. This type mismatch may cause downstream query issues when joining or filtering across event types. Consider either:
1. Renaming to 'model_list' or 'models' to distinguish from singular model references
2. If this truly represents multiple models, document this deviation and ensure downstream consumers handle the array type appropriately

**Fields:** models_used

## !! Standardize common metadata field naming

Several metadata fields use non-canonical naming patterns that differ from established conventions:

- '_tenant_id' → canonical is 'tenant_id' (though '_tenant_id' is commonly used)
- '_service_id' → canonical is 'service_id'
- '_event_id' → canonical is '_correlation_id' (other types use both '_correlation_id' and '_event_id')
- '_home_pop' → other types also use '_gef_home_pop'

Recommendation: For new schemas, prefer the canonical names unless there's a specific reason to maintain consistency with a particular event family. Document the choice if deviating.

**Fields:** _tenant_id, _home_pop, _service_id, _event_id

## !! Use canonical process field names without 'client_' prefix

Process-related fields use a 'client_' prefix that deviates from canonical naming:

- 'client_pid' → canonical is 'pid'
- 'client_comm' → canonical is 'comm'
- 'client_args' → canonical is 'args'
- 'client_uid' → canonical is 'uid'

While the prefix provides context (these describe the MCP client process), most other event types use the unprefixed versions. Consider:
1. Using canonical names if the context is clear from the message type
2. If you need to distinguish client vs server process info, use nested messages (e.g., 'client.pid', 'client.comm') for better structure

**Fields:** client_pid, client_comm, client_args, client_uid

## !! Standardize data transfer byte field naming

The field 'total_bytes' maps to the 'data_transfer_bytes' concept where the canonical name is 'bytes_transferred'. Other event types use 'numbytes', 'server_bytes', and 'total_bytes'. Additionally, the type is 'uint64' while the canonical type is 'int64' (compatible but not exact).

Recommendation: Consider using 'bytes_transferred' for better cross-schema consistency, or document why 'total_bytes' is preferred for this context.

**Fields:** total_bytes

## !! Align AI model field naming with canonical pattern

The field 'models_used' maps to 'ai_model_identifier' concept. Canonical name is 'model'. Other event types use: 'model', 'cs_model', 'rs_model', 'model_name', 'models_used'.

Since this is a repeated field representing multiple models, consider 'models' (plural of canonical) to maintain consistency while indicating multiplicity.

**Fields:** models_used

## ! Consider adding sample data fields using canonical naming

The fields 'sampling_request_sample' and 'sampling_response_sample' map to 'data_samples' concept. Other event types use: 'request_sample', 'response_sample', 'args_sample', 'result_sample'.

Consider using 'request_sample' and 'response_sample' for consistency with other schemas that capture similar sampling data.

**Fields:** sampling_request_sample, sampling_response_sample

## ! Align server metadata field naming

Several server-related fields have naming that could be aligned with existing patterns:

- 'server_name' → canonical 'name' for component_name concept (other types use 'name')
- 'server_version' → similar to 'client_version' in ClientStatus
- 'server_endpoint' → similar to 'command' in McpServer

These are informational suggestions - the current naming is descriptive and may be appropriate for this schema's context.

**Fields:** server_name, server_version, server_endpoint

## ! Consider aligning tool-related field naming

Tool-related fields have similar counterparts in other schemas:

- 'tools_available' → similar to 'tools' in McpServer
- 'tools_invoked' → similar to 'args' in McpServer
- 'tool_calls' → similar to 'tools' in McpServer

Consider whether these could use consistent naming with McpServer schema for better cross-schema queries.

**Fields:** tools_available, tools_invoked, tool_calls

## ! Resource URI field naming alignment

The field 'resource_uris' is similar to '_urls' in AppEnriched. Consider whether alignment with the '_urls' pattern or a more descriptive name like 'accessed_resource_uris' would improve clarity and consistency.

**Fields:** resource_uris

## ! Missing concepts are expected for specialized event type

The analysis flagged many missing concepts (270+), but this is expected for a specialized 'MCPSession' event type. Not every event type needs every concept.

However, consider whether the following commonly-expected concepts should be added based on the MCP session context:

- 'user_identity' - Who initiated the MCP session?
- 'device_identifier' - What device is the MCP client running on?
- 'network_endpoint' - Network connection details for the session
- 'process_information' - Already partially covered by client_* fields
- 'token_usage_metrics' - If tracking AI token consumption
- 'tool_invocation' - Detailed tool call tracking (may overlap with existing fields)

Review these concepts and add only those that are relevant to your use case.

