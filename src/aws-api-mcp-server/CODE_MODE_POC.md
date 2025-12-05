# AWS API MCP Server - Code Mode POC

## Overview

This POC introduces "Code Mode" to the AWS API MCP Server, allowing AI agents to write Python code that calls AWS operations instead of using individual tool calls. This approach dramatically improves efficiency for multi-step AWS workflows while maintaining security and error resilience.

## Problem Statement

Current MCP usage suffers from two key inefficiencies:

1. **Token Bloat**: Each AWS operation requires separate tool calls, with intermediate results flowing through the LLM context
2. **Brittle Workflows**: Single command failures break entire multi-step procedures
3. **Limited Data Processing**: Large AWS responses consume context without ability to filter/transform

### Example: Traditional Approach (Inefficient)
```
TOOL CALL: call_aws("ec2 describe-instances")
→ Returns 50KB of instance data to LLM context

TOOL CALL: call_aws("ec2 describe-volumes --filters Name=attachment.instance-id,Values=i-123,i-456,i-789")  
→ LLM must copy instance IDs from previous response
→ Returns another 30KB of volume data to context

TOOL CALL: call_aws("cloudwatch get-metric-statistics ...")
→ More data copying and context bloat
```

**Result**: 150KB+ tokens, multiple round trips, fragile error handling

## Solution: Code Mode

Enable agents to write Python code that calls AWS operations directly:

```python
# Single tool call with embedded logic
instances = aws("ec2 describe-instances")
running_instances = [i for r in instances.get("Reservations", []) 
                    for i in r.get("Instances", []) 
                    if i.get("State", {}).get("Name") == "running"]

print(f"Found {len(running_instances)} running instances")

for instance in running_instances:
    volumes = aws(f"ec2 describe-volumes --filters Name=attachment.instance-id,Values={instance['InstanceId']}")
    print(f"Instance {instance['InstanceId']}: {len(volumes.get('Volumes', []))} volumes")
```

**Result**: 2KB tokens, single round trip, resilient execution

## Benefits

### 1. **Massive Token Reduction**
- **Before**: 150,000+ tokens for complex workflows
- **After**: 2,000-5,000 tokens for equivalent functionality
- **Savings**: 95%+ reduction in token usage and costs

### 2. **Error Resilience** 
- Individual command failures don't break entire workflows
- Graceful degradation with continued execution
- Better error context and handling

### 3. **Enhanced Data Processing**
- Filter and transform AWS responses before returning to LLM
- Complex logic (loops, conditionals) in familiar Python syntax
- No context window limitations for large datasets

### 4. **Improved Developer Experience**
- More intuitive than chaining CLI commands
- Leverages LLM's strong Python capabilities
- Familiar programming patterns vs. synthetic tool calling

## References

This approach is inspired by recent research and implementations:

1. **Anthropic Engineering Blog**: [Code execution with MCP: Building more efficient agents](https://www.anthropic.com/engineering/code-execution-with-mcp)
   - Documents 98.7% token reduction using code execution vs direct tool calls
   - Demonstrates superior LLM performance with code vs synthetic tool calling

2. **Cloudflare Blog**: [Code Mode: the better way to use MCP](https://blog.cloudflare.com/code-mode/)
   - Shows LLMs excel at writing code against APIs vs using tool calls
   - "LLMs have seen a lot of code. They have not seen a lot of tool calls."

## POC Implementation

### Core Feature
Single new tool: `execute_aws_python(code, dry_run=False)`

### Execution Environment
- Local Python sandbox using `exec()` with restricted globals
- Available functions: `aws(command)`, `print(message)`
- Reuses existing AWS API MCP server infrastructure

### Security
- Leverages existing consent and validation mechanisms
- Batch consent for all AWS operations in code
- Restricted execution environment

## Example Use Cases

### 1. Infrastructure Audit
```python
# Get all EC2 instances and their security groups
instances = aws("ec2 describe-instances")
security_issues = []

for reservation in instances.get("Reservations", []):
    for instance in reservation.get("Instances", []):
        sg_ids = [sg["GroupId"] for sg in instance.get("SecurityGroups", [])]
        
        for sg_id in sg_ids:
            sg = aws(f"ec2 describe-security-groups --group-ids {sg_id}")
            rules = sg.get("SecurityGroups", [{}])[0].get("IpPermissions", [])
            
            for rule in rules:
                if any(ip.get("CidrIp") == "0.0.0.0/0" for ip in rule.get("IpRanges", [])):
                    security_issues.append({
                        "instance": instance["InstanceId"],
                        "security_group": sg_id,
                        "issue": "Open to internet"
                    })

print(f"Found {len(security_issues)} security issues")
for issue in security_issues:
    print(f"⚠️  {issue['instance']}: {issue['issue']}")
```

### 2. Cost Optimization
```python
# Find unused EBS volumes
volumes = aws("ec2 describe-volumes")
unused_volumes = []
total_cost = 0

for volume in volumes.get("Volumes", []):
    if volume.get("State") == "available":  # Not attached
        size = volume.get("Size", 0)
        volume_type = volume.get("VolumeType", "gp2")
        
        # Simple cost calculation (gp2 = $0.10/GB/month)
        monthly_cost = size * 0.10 if volume_type == "gp2" else size * 0.125
        total_cost += monthly_cost
        
        unused_volumes.append({
            "id": volume["VolumeId"],
            "size": size,
            "cost": monthly_cost
        })

print(f"Found {len(unused_volumes)} unused volumes")
print(f"Potential monthly savings: ${total_cost:.2f}")
```

### 3. Deployment Verification
```python
# Verify deployment across multiple regions
regions = ["us-east-1", "us-west-2", "eu-west-1"]
deployment_status = {}

for region in regions:
    # Check if application load balancer exists
    albs = aws(f"elbv2 describe-load-balancers --region {region}")
    
    app_albs = [alb for alb in albs.get("LoadBalancers", []) 
                if "app" in alb.get("LoadBalancerName", "").lower()]
    
    deployment_status[region] = {
        "load_balancers": len(app_albs),
        "healthy": len(app_albs) > 0
    }

print("Deployment Status:")
for region, status in deployment_status.items():
    status_icon = "✅" if status["healthy"] else "❌"
    print(f"{status_icon} {region}: {status['load_balancers']} load balancers")
```

## Success Metrics

### Quantitative
- **Token Reduction**: 50%+ fewer tokens vs equivalent multi-tool approach
- **Execution Time**: Faster due to reduced round trips
- **Error Rate**: Lower failure rate due to resilient execution

### Qualitative  
- **Developer Experience**: More intuitive workflow creation
- **Maintainability**: Easier to understand and modify procedures
- **Flexibility**: Complex logic patterns not possible with tool chains

## Next Steps

After POC validation:

1. **Enhanced Sandboxing**: Docker/Lambda execution environments
2. **Procedure Persistence**: Save and reuse common workflows  
3. **Advanced Dry-Run**: Cost estimation and impact analysis
4. **Type Safety**: Add AWS SDK type hints and validation
5. **Integration**: Seamless workflow with existing MCP tools

## Getting Started

1. Add the POC implementation to `server.py`
2. Test with simple AWS operations
3. Gradually increase complexity
4. Measure token usage improvements
5. Gather user feedback on developer experience

---

*This POC demonstrates the transformative potential of Code Mode for AWS automation while maintaining the security and reliability of the existing AWS API MCP Server.*
