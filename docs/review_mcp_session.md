# Proto Review: /Users/qzou/git/ef-client/protos/aidiscovery/mcp_session.proto

**Issues:** 332 (11 errors, 321 warnings, 0 info)

## !!! Fix type mismatch for 'timestamp' field

The 'timestamp' field is defined as 'int64' but the canonical type for event metadata timestamps is 'string'. This type inconsistency may cause downstream query issues when joining or comparing with other event types. Consider changing to a string type (e.g., ISO 8601 format) or using a well-defined timestamp message type for consistency across the platform.

**Fields:** timestamp

## !!! Fix type mismatch for 'client_pid' field

The 'client_pid' field is defined as 'uint32' but maps to the 'device_identity' concept which uses 'string' type canonically. While process IDs are naturally numeric, for cross-event-type consistency and to support heterogeneous device identifiers, consider either: (1) using a string type, or (2) renaming to clarify this is specifically a process ID rather than a general device identifier.

**Fields:** client_pid

## !!! Fix type mismatch for 'client_uid' field

The 'client_uid' field is defined as 'uint32' but maps to 'application_identifier' which canonically uses 'string'. Unix user IDs are numeric, but this field name suggests application identification. Either rename to 'client_user_id' to clarify intent, or change the type to string if this represents an application name/identifier.

**Fields:** client_uid

## !!! Fix type mismatch for 'server_version' field

The 'server_version' field is defined as 'string' but was matched to 'file_metadata' concept which expects an 'object' type. This appears to be a semantic mismatch - server_version likely represents a version string, not file metadata. The field type is probably correct, but ensure downstream consumers understand this is a simple version string.

**Fields:** server_version

## !!! Fix type mismatch for 'messages_exchanged' field

The 'messages_exchanged' field is defined as 'uint32' but was matched to 'conversation_tracking' which uses 'string' type (for conversation IDs). This is a semantic mismatch - messages_exchanged is clearly a count. Consider adding a 'conversation_id' field if conversation tracking is needed, and keep messages_exchanged as a counter.

**Fields:** messages_exchanged

## !!! Fix type mismatch for 'process' field

The 'process' field uses 'ProcessContext' message type but was matched to 'process_arguments' which expects 'string'. This appears to be a semantic mismatch - ProcessContext is richer than just arguments. The current structured type is likely appropriate; consider if the message contains an 'args' field for consistency with other event types.

**Fields:** process

## !!! Fix type mismatch for 'tool_calls' field

The 'tool_calls' field uses 'McpToolCall' message type but was matched to 'http_method' which expects 'string'. This is a semantic mismatch - tool_calls represents MCP tool invocations, not HTTP methods. The structured type is correct for this use case.

**Fields:** tool_calls

## !!! Fix type mismatch for 'files_accessed' field

The 'files_accessed' field uses 'FileAccess' but canonical type expects 'repeated FileAccess'. Ensure this field is marked as 'repeated' in the proto definition to capture multiple file access events per session.

**Fields:** files_accessed

## !!! Fix type mismatch for 'sampling_observed' field

The 'sampling_observed' field is defined as 'bool' but was matched to 'sample_data' which expects 'bytes'. This is a semantic mismatch - 'sampling_observed' is a flag indicating whether sampling occurred, while 'sample_data' contains actual samples. The bool type is correct for a flag; the field name clearly indicates its purpose.

**Fields:** sampling_observed

## !!! Fix type mismatch for sampling sample fields

The 'sampling_request_sample' and 'sampling_response_sample' fields are defined as 'bytes' but were matched to 'data_transfer_bytes' which expects 'uint64' (a count). These fields contain actual sample data, not byte counts. Consider adding separate fields like 'sampling_request_bytes' and 'sampling_response_bytes' as uint64 if byte counts are needed.

**Fields:** sampling_request_sample, sampling_response_sample

## !! Consider standardizing tenant identifier field name

The '_tenant_id' field uses an underscore prefix while the canonical name is 'tenant_id'. Other event types use both conventions. For new event types, prefer 'tenant_id' without the underscore prefix unless there's a specific reason for the underscore (e.g., indicating a system-populated field).

**Fields:** _tenant_id

## !! Standardize event identifier field naming

The fields '_service_id' and '_event_id' both map to 'event_identifier' concept. The canonical name is 'event_id' and other event types consistently use '_event_id'. Consider: (1) Keep '_event_id' as the event identifier, (2) Rename '_service_id' to clarify its purpose (e.g., 'service_name' or 'service_type') if it represents something different from the event ID.

**Fields:** _service_id, _event_id

## !! Standardize session timestamp field names

The fields 'session_start_ns' and 'session_end_ns' use nanosecond suffixes. Other event types use 'app_session_id' for session tracking. Consider using more standard naming like 'session_start_timestamp' and 'session_end_timestamp', or document the nanosecond precision clearly in field comments.

**Fields:** session_start_ns, session_end_ns

## ! Consider renaming MCP-specific fields for clarity

Fields like 'transport_type', 'client_comm', 'client_args', 'tools_available', 'tools_invoked' have domain-specific meanings in the MCP context that don't directly map to existing canonical concepts. This is acceptable for a new event type. Add clear documentation comments explaining the MCP-specific semantics of these fields.

**Fields:** transport_type, client_comm, client_args, tools_available, tools_invoked

## !! Align 'models_used' with AI model naming conventions

The 'models_used' field matches the 'ai_model_identifier' concept. Other event types use variations like 'model_name', 'model', 'cs_model'. For consistency, consider renaming to 'model_names' (plural indicating multiple models) or keeping 'models_used' with clear documentation.

**Fields:** models_used

## !! Align 'protocol_version' with network protocol conventions

The 'protocol_version' field maps to 'network_protocol' concept where canonical name is 'protocol'. Consider whether this represents the MCP protocol version specifically. If so, 'mcp_protocol_version' would be clearer. Other event types use 'protocol' for network protocols.

**Fields:** protocol_version

## !! Consider adding common event metadata fields

This event type is missing several commonly-used concepts that would improve integration with existing analytics: 'source_ip_address' (user's IP), 'user_agent' (client identification), 'correlation_identifier' (for tracing related events), and 'event_received_timestamp' (processing timestamp). Consider adding these if applicable to MCP session tracking.

## ! Consider adding geolocation fields

Many other event types include geolocation information (source_geolocation, geographic_location). If MCP sessions can be associated with user locations, consider adding these fields to enable geographic analysis and compliance reporting.

## ! Consider adding DLP/security classification fields

Given this event tracks AI tool interactions and file access, consider adding 'data_classification' or 'dlp_classification' fields to support data loss prevention analysis of AI-assisted workflows.

## ! Add token usage metrics for AI operations

Other AI-related event types (aig.v2/AigApplicationEvent, aidiscovery/PromptRound) include 'token_usage_metrics' for tracking AI token consumption. Consider adding similar fields to track token usage across MCP sessions for cost attribution and usage analysis.

