# Proto Review: /Users/qzou/git/ef-client/protos/aidiscovery/mcp_session.proto

**Issues:** 315 (1 errors, 305 warnings, 9 info)

## !!! Fix type mismatch for 'files_accessed' field

The field 'files_accessed' has type 'FileAccess' but the canonical type for 'file_access_events' concept is 'repeated FileAccess'. This type mismatch may cause downstream query issues when joining or aggregating data across event types. Change the field type from 'FileAccess' to 'repeated FileAccess' to maintain consistency with other event types that track file access events.

**Fields:** files_accessed

## !! Standardize client process fields to use canonical naming

Several client process-related fields use a 'client_' prefix while other event types use shorter canonical names. Consider aligning these field names for cross-schema consistency:

- 'client_pid' → canonical is 'pid' (used by most other event types)
- 'client_comm' → canonical is 'comm'
- 'client_args' → canonical is 'args'
- 'client_uid' → canonical is 'uid'

If the 'client_' prefix is intentional to distinguish from server-side process info, document this convention. Otherwise, rename to match the canonical pattern used across the codebase.

**Fields:** client_pid, client_comm, client_args, client_uid

## !! Align session timing field naming

The field 'session_end_ns' maps to the 'session_timing' concept where the canonical name is 'session_start_ns'. Other event types use a mix of: session_start_ns, session_end_ns, start_time, end_time, session_duration. Ensure that if you have 'session_end_ns', you also have a corresponding 'session_start_ns' field, and consider whether the '_ns' suffix (nanoseconds) is consistent with your timing precision requirements.

**Fields:** session_end_ns

## !! Standardize AI model identifier field naming

The field 'models_used' maps to the 'ai_model_identifier' concept where the canonical name is 'model_name'. Other event types use: model_name, models_used, model, cs_model, rs_model. For consistency with the majority of event types, consider whether 'model_name' (singular) or 'models_used' (plural, indicating multiple models) better represents your data. If multiple models can be used in a session, 'models_used' as a repeated field is appropriate, but document this deviation from the canonical singular form.

**Fields:** models_used

## !! Review underscore-prefixed system fields for consistency

Several system metadata fields use underscore prefixes with slight naming variations:

- '_tenant_id' - canonical is 'tenant_id' (mixed usage across event types)
- '_home_pop' - canonical is 'home_pop' (consistent with other event types)
- '_service_id' - maps to 'event_metadata' concept, but canonical is 'event_id'
- '_event_id' - canonical is 'event_id' (consistent)

The underscore prefix convention appears intentional for system fields. Ensure '_service_id' is correctly named - if it represents a service identifier rather than an event ID, it may need a different concept mapping.

**Fields:** _tenant_id, _home_pop, _service_id, _event_id

## ! Consider aligning tool-related field naming

The fields 'tools_available' and 'tools_invoked' map to the 'tool_definition' concept where the canonical name is 'tool_info'. Other event types use: tool_name, name, description, input_schema, type. These field names are descriptive and contextually clear for MCP sessions. If these are collections of tool definitions, the current naming is acceptable, but ensure the nested structure aligns with the ToolDefinition message type used elsewhere.

**Fields:** tools_available, tools_invoked

## ! Review sampling field naming for consistency

The fields 'sampling_request_sample' and 'sampling_response_sample' map to the 'sample_data' concept. Other event types use: request_sample, response_sample, args_sample, result_sample. Consider shortening to 'request_sample' and 'response_sample' to match the established pattern, unless the 'sampling_' prefix provides important semantic distinction specific to MCP sampling operations.

**Fields:** sampling_request_sample, sampling_response_sample

## ! Consider semantic similarity with existing fields

Several fields have semantic overlap with fields in other schemas:

- 'server_name' is similar to 'hostname' in NetworkEnriched
- 'server_version' is similar to 'client_version' in ClientStatus
- 'protocol_version' is similar to 'os_version' in NetworkEnriched
- 'tool_calls' is similar to 'tool_name' in McpToolCall
- 'resource_uris' is similar to 'url' in NetworkEnriched

These are informational - the current names may be appropriate for MCP session context. Review whether any of these could benefit from alignment with existing naming patterns for easier cross-schema queries.

**Fields:** server_name, server_version, protocol_version, tool_calls, resource_uris

## !! Missing common observability fields

The MCPSession event type is missing several common observability and tracking concepts that are present in other event types. Consider adding these fields if applicable to MCP session monitoring:

**High Priority (commonly expected):**
- Event correlation ID for linking related events
- Creation/insertion timestamps for event lifecycle tracking
- Event source identifier

**Medium Priority (for enrichment):**
- Geographic location information (if client location is relevant)
- Network endpoint details (source/destination IP, port)
- User identity information

Evaluate which of these concepts apply to MCP session telemetry and add the relevant fields.

## !! Missing security and compliance fields

For AI/MCP session monitoring, consider whether security and compliance fields are needed:

- DLP classification (if sensitive data may be processed)
- Policy identifier/reference (if governance policies apply)
- User identity and organizational unit (for access control auditing)
- Data classification labels

These fields are present in other application event types and may be relevant for AI governance and security monitoring use cases.

