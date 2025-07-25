# AWS API MCP Agent Scripts

## Overview

The AWS API MCP Agent Scripts feature addresses a fundamental challenge in AI-powered AWS automation: enabling teams to create and share reusable automation workflows without the overhead of building complete MCP servers. This system provides a lightweight, flexible solution that extends the existing aws-api-mcp-server with custom scripts that AI agents can discover and execute.

## Problem Statement

### Current Challenges
- **Proliferation of AWS MCP Servers**: Creating full MCP servers for specific service automation tasks requires significant time investment for server implementation, tool definitions, publication, and advertising, resulting in dozens of servers customers must reason about.
- **Lack of Agent Expertise**: LLM agents working with AWS often need to execute multiple related commands in sequence for common tasks, but lack guidance on proper ordering, error handling, and best practices.
- **Maintenance Overhead**: Custom servers entail ongoing maintenance, regular updates, and security management. Creating workflow files is a low-effort alternative that leverages continuous LLM improvements.

## Solution Approach

The system takes a **declarative, agent-driven approach** to workflow execution. Rather than building complex execution engines or compilation pipelines, it leverages the natural language understanding and reasoning capabilities of LLM agents along with existing low-level tools (like the `call_aws` tool for executing AWS CLI commands).

### Key Principles
- **Agent-Driven**: Workflows provide structured guidance while agents retain full control over execution and error handling
- **Declarative**: JSON-based workflow definitions eliminate complex build processes
- **Extensible**: Seamless integration with existing AWS API MCP tools and third-party MCP servers
- **Maintainable**: Simple JSON files are easy to read, write, and maintain

## Architecture

### Core Components

#### 1. Workflow Registry (`core/workflows/registry.py`)
- Scans workflow JSON files from the `workflows_registry` directory at server startup
- Provides in-memory storage and efficient retrieval
- Dynamically generates workflow listings for tool descriptions

#### 2. Workflow Models (`core/workflows/models.py`)
- `WorkflowStep`: Individual step with name, description, tool reference, and parameter hints
- `Workflow`: Complete workflow with metadata and ordered steps

#### 3. JSON Validator (`core/workflows/json_validator.py`)
- Validates workflow JSON against comprehensive schema
- Provides detailed error messages for debugging
- Supports both file and string validation

#### 4. New MCP Tool: `get_workflow_plan`
- Exposes available workflows in its tool description
- Returns structured workflow plans for LLM execution
- Instructs agents to prefer workflows over direct AWS CLI calls when applicable

## Workflow Structure

Workflows are defined using a simple JSON structure:

```json
{
  "name": "unique_workflow_id",
  "short_description": "Brief description for LLM intent matching",
  "description": "Detailed workflow explanation and context",
  "steps": [
    {
      "name": "step_name",
      "description": "Natural language description of what needs to be done",
      "use_tool": "call_aws",
      "tool_parameter_hints": {
        "command": "aws cli command or natural language hint",
        "parameter": "Hint for LLM parameter generation"
      }
    }
  ]
}
```

### Flexible Parameter Handling

The system supports both explicit commands and natural language hints:

```json
// Explicit command
{
  "use_tool": "call_aws",
  "tool_parameter_hints": {
    "command": "aws s3api list-buckets"
  }
}

// Natural language hint
{
  "use_tool": "call_aws",
  "tool_parameter_hints": {
    "command": "AWS CLI to list buckets"
  }
}
```

## Included Workflow Examples

### 1. Log Group Analysis (`log-group-analysis.json`)
- Analyzes CloudWatch log groups for anomalies and patterns
- Discovers anomaly detectors and retrieves anomalies
- Performs CloudWatch Logs Insights queries for pattern analysis
- Demonstrates complex multi-step workflow with result chaining

### 2. EC2 Security Check (`ec2-security-check.json`)
- Lists EC2 instances in a region
- Analyzes security group configurations for compliance
- Simple two-step workflow example

### 3. S3 Lifecycle Setup (`s3-lifecycle-setup.json`)
- Verifies S3 bucket existence and configuration
- Configures lifecycle rules for cost optimization
- Demonstrates parameter passing between steps

### 4. RDS Backup (`rds-backup.json` and `rds-backup-simple.json`)
- Simple and complex RDS backup automation examples
- Shows workflow complexity variations

## Real-World Impact

This feature eliminates the need for specialized MCP servers for common automation tasks. For example, the official CloudWatch MCP Server currently requires a dedicated `analyze_log_group` tool. With AWS API MCP Agent Scripts, this functionality can be implemented as a reusable workflow script, eliminating server development and maintenance overhead.

## JSON Schema Validation

The system includes comprehensive JSON schema validation that enforces:

- **Required Fields**: name, short_description, description, steps
- **String Constraints**: Length limits and pattern validation
- **Structure Validation**: Proper step formatting and required properties
- **Extensibility**: Flexible tool_parameter_hints for various use cases

## Integration

### Server Integration
The feature integrates seamlessly with the existing aws-api-mcp-server:
- Workflows are automatically discovered at server startup
- The `get_workflow_plan` tool is dynamically populated with available workflows
- Existing security and validation mechanisms are preserved

### Agent Usage
LLM agents interact with workflows through the standard MCP protocol:
1. Agent discovers available workflows via `get_workflow_plan` tool description
2. Agent calls `get_workflow_plan` with specific workflow_id
3. Agent receives structured workflow plan with step-by-step instructions
4. Agent executes steps using existing tools (primarily `call_aws`)

## Benefits

### For Teams
- **Reduced Development Overhead**: No need to create custom MCP servers
- **Shared Knowledge**: Workflows capture and share automation best practices
- **Rapid Deployment**: JSON files can be created and deployed quickly

### For Users
- **Consistent Experience**: Standardized automation patterns across services
- **Improved Reliability**: Pre-tested workflows reduce errors
- **Better Guidance**: Step-by-step instructions help agents execute complex tasks

### For the Ecosystem
- **Reduced Server Proliferation**: Fewer specialized MCP servers to maintain
- **Leveraged Innovation**: Benefits from continuous LLM improvements
- **Community Contribution**: Easy for teams to contribute workflows

## Limitations and Considerations

### Current Limitations
- **Agent Dependency**: Execution quality depends on LLM agent capabilities
- **No Advanced Orchestration**: No built-in parallel execution, complex retry logic, or conditional branching
- **Limited Validation**: Relies on agent understanding rather than strict semantic validation

### Design Trade-offs
- **Simplicity vs. Power**: Chose simplicity and maintainability over advanced workflow features
- **Flexibility vs. Validation**: Allows natural language hints but requires careful workflow design
- **Agent Trust**: Relies on agent intelligence for parameter resolution and error handling

## Future Extensibility

The architecture supports future enhancements:
- **Custom Workflow Directories**: Support for customer-provided workflow folders
- **Third-Party Tool Integration**: Workflows can reference any MCP tool
- **Enhanced Validation**: Potential for semantic validation improvements
- **Workflow Composition**: Possible support for workflow chaining or nesting

## Getting Started

### Adding New Workflows
1. Create a JSON file in `workflows_registry/` directory
2. Follow the JSON schema structure
3. Validate using the built-in validator
4. Restart the server to register the new workflow

### Workflow Development Best Practices
- Use clear, descriptive names and descriptions
- Provide helpful parameter hints for agents
- Test workflows with different LLM agents
- Document complex parameter relationships
- Consider error scenarios in step descriptions

## Conclusion

AWS API MCP Agent Scripts represents a pragmatic solution to AWS automation workflow sharing. By leveraging LLM capabilities and maintaining simplicity in workflow definition, it provides immediate value while positioning for future enhancements as AI agent capabilities continue to evolve.

The system successfully balances flexibility with structure, enabling teams to capture and share automation knowledge without the overhead of custom server development, while providing AI agents with the guidance they need to execute complex AWS operations reliably.
