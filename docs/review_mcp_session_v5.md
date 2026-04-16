# Proto Review: /Users/qzou/git/ef-client/protos/aidiscovery/mcp_session.proto

**Issues:** 321 (1 errors, 310 warnings, 10 info)

## !!! Critical: Fix _tenant_id type inconsistency across schema

The field '_tenant_id' is defined as 'int32' in this proto, but other event types use 'string' (DiscoveryApplicationEvent, PhoenixApplicationEvent, UIAPIGWAuditLogEvent). This type mismatch will cause downstream query failures when joining across event types.

**Recommendation:** Standardize on 'string' type for tenant_id across all schemas, as string is more flexible and matches the majority of existing implementations. If int32 is required for performance reasons, create a migration plan to update all schemas consistently.

**Fields:** _tenant_id

## !!! Fix models_used type mismatch - should be singular string

The field 'models_used' is defined as 'repeated string' but the canonical type for 'ai_model_identifier' concept is 'string'. Other event types use singular 'model' or 'model_name'.

**Recommendation:** Either:
1. Rename to 'models' (plural) if multiple models are needed and update the concept definition
2. Change to singular 'model' field of type 'string' to match canonical pattern
3. If multiple models are genuinely needed, consider a wrapper message type for richer metadata

**Fields:** models_used

## !! Standardize process-related field naming

Multiple fields use 'client_' prefix inconsistently with the canonical naming convention:
- 'client_pid' → canonical is 'pid'
- 'client_comm' → canonical is 'comm'
- 'client_args' → canonical is 'args'
- 'client_uid' → canonical is 'uid'

**Recommendation:** Since this is an MCP session tracking the client process, the 'client_' prefix provides valuable context. Consider either:
1. Adopting a nested message structure: `ProcessInfo client` with fields `pid`, `comm`, `args`, `uid`
2. Or updating the canonical naming to allow 'client_' prefixed variants for client-side process context

**Fields:** client_pid, client_comm, client_args, client_uid

## !! Align _event_id with correlation_id convention

The field '_event_id' maps to 'event_correlation' concept where the canonical name is '_correlation_id'. Other event types use '_correlation_id' or '_id'.

**Recommendation:** Rename '_event_id' to '_correlation_id' for consistency with other event types. If a separate event identifier is needed distinct from correlation, consider adding both fields with clear documentation of their purposes.

**Fields:** _event_id

## !! Standardize total_bytes field type and naming

The field 'total_bytes' has two issues:
1. Type is 'uint64' but canonical type is 'int64' (compatible but not exact)
2. Canonical name is 'bytes_transferred'; other types use 'numbytes', 'server_bytes'

**Recommendation:** 
1. Change type to 'int64' for consistency (uint64 can cause issues with some downstream systems)
2. Consider renaming to 'bytes_transferred' or keeping 'total_bytes' and updating schema documentation to recognize it as an alias

**Fields:** total_bytes

## !! Fix 'type' field type divergence

The 'type' field is defined as 'string' here, but GenericStreamRequest uses an 'EventType' enum. This inconsistency can cause query failures when joining across schemas.

**Recommendation:** Consider using an enum type for 'type' if the values are from a known set, or ensure string values match enum names exactly. Document the expected values clearly.

**Fields:** type

## ! Consider aligning server_* fields with canonical naming

Several server-related fields have similar concepts elsewhere:
- 'server_name' → canonical 'name' (component_name concept)
- 'server_version' → similar to 'client_version' in ClientStatus
- 'server_endpoint' → similar to 'command' in McpServer

**Recommendation:** These fields are appropriately prefixed for clarity in an MCP session context. Consider creating a nested 'McpServerInfo' message to group these fields, which would align better with component patterns elsewhere.

**Fields:** server_name, server_version, server_endpoint

## ! Align tool-related fields with McpServer conventions

Several tool fields have similar counterparts in McpServer:
- 'tools_available' → similar to 'tools' in McpServer
- 'tools_invoked' → similar to 'args' in McpServer
- 'tool_calls' → similar to 'tools' in McpServer

**Recommendation:** Consider aligning naming with McpServer for consistency. If 'tools_available' represents the list of tools, rename to 'tools'. Use 'tool_calls' consistently for invocation records. Document the distinction between available tools and invoked tools clearly.

**Fields:** tools_available, tools_invoked, tool_calls

## ! Align sample data fields with canonical pattern

Fields 'sampling_request_sample' and 'sampling_response_sample' map to 'data_samples' concept. Other event types use: 'request_sample', 'response_sample', 'args_sample', 'result_sample'.

**Recommendation:** Rename to 'request_sample' and 'response_sample' to match the established pattern in other event types. The 'sampling_' prefix is redundant.

**Fields:** sampling_request_sample, sampling_response_sample

## !! Consider adding common event metadata fields

This event type is missing several commonly-used concepts that would improve cross-schema queryability:

**High Priority (for event correlation):**
- 'correlation_identifier' - for tracing related events
- 'creation_timestamp' / 'insertion_timestamp' - for pipeline tracking
- 'source_ip_address' / 'destination_ip_address' - for network context

**Medium Priority (for enrichment):**
- 'user_identity' - who initiated the session
- 'device_identifier' - which device
- 'application_identifier' - application context

**Recommendation:** Add at minimum: correlation_id, creation timestamp, and user/device identifiers to enable standard event correlation and enrichment workflows.

## ! Consider adding AI-specific context fields

As an MCP session event for AI discovery, consider adding fields that other AI-related event types have:

- 'token_usage_metrics' - for tracking AI resource consumption
- 'detection_confidence' - for AI classification confidence
- 'ai_model' - detailed model information beyond just names
- 'tool_invocation' - structured tool call information

**Recommendation:** Review aidiscovery/PromptRound and aidiscovery/AIServiceInteraction for patterns that could enhance this event type's utility for AI observability.

