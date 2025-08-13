#!/usr/bin/env python3
"""
Jira Ticket Fetcher - Fetches ticket descriptions and acceptance criteria using JQL
"""

import os
import requests
import json
import re
from base64 import b64encode
from typing import List, Dict, Any, Optional
import anthropic

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Install with: pip install python-dotenv")
    print("Falling back to system environment variables...")

class JiraTicketFetcher:
    def __init__(self, jira_url: str, email: str, api_token: str):
        self.jira_url = jira_url.rstrip('/')
        self.email = email
        self.api_token = api_token
        self.auth_header = self._create_auth_header()
        
    def _create_auth_header(self) -> str:
        """Create basic auth header for Jira API"""
        credentials = f"{self.email}:{self.api_token}"
        encoded_credentials = b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    
    def search_tickets(self, jql: str, fields: List[str] = None) -> Dict[str, Any]:
        """Search for tickets using JQL query"""
        if fields is None:
            fields = ["summary", "description", "key", "status", "assignee"]
        
        url = f"{self.jira_url}/rest/api/3/search"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        payload = {
            "jql": jql,
            "fields": fields,
            "maxResults": 100  # Adjust as needed
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return {}
    
    def get_field_info(self) -> Dict[str, Any]:
        """Get all available fields to find custom field IDs"""
        url = f"{self.jira_url}/rest/api/3/field"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching fields: {response.status_code} - {response.text}")
            return []
    
    def find_acceptance_criteria_field(self) -> str:
        """Find the field ID for Acceptance Criteria"""
        # Use environment variable if set, otherwise search
        ac_field_id = os.getenv('ACCEPTANCE_CRITERIA_FIELD')
        if ac_field_id:
            print(f"Using specified Acceptance Criteria field: {ac_field_id}")
            return ac_field_id
        
        fields = self.get_field_info()
        
        # Common names for acceptance criteria fields
        ac_field_names = [
            "acceptance criteria",
            "acceptancecriteria", 
            "acceptance_criteria",
            "ac",
            "criteria",
            "definition of done",
            "dod"
        ]
        
        print("\nSearching for Acceptance Criteria field...")
        found_field = None
        
        for field in fields:
            field_name = field.get('name', '').lower()
            if any(ac_name in field_name for ac_name in ac_field_names):
                print(f"Found potential AC field: {field['name']} (ID: {field['id']})")
                found_field = field['id']
                break
        
        if not found_field:
            print("No exact Acceptance Criteria field found. Available custom fields:")
            custom_fields = [f for f in fields if f['id'].startswith('customfield_')]
            for field in custom_fields[:15]:  # Show first 15 custom fields
                print(f"  - {field['name']} (ID: {field['id']})")
            
            # Let user choose a field if running interactively
            try:
                field_choice = input("\nEnter field ID to use for Acceptance Criteria (or press Enter to skip): ").strip()
                if field_choice:
                    found_field = field_choice
            except EOFError:
                pass
        
        return found_field
    
    def find_development_field(self) -> str:
        """Find the field ID for Development section"""
        fields = self.get_field_info()
        
        print("\nSearching for Development field...")
        print("Looking for fields that might contain development/PR data...")
        
        # Look for development-related fields
        dev_candidates = []
        
        for field in fields:
            field_name = field.get('name', '').lower()
            field_id = field.get('id', '')
            field_type = field.get('schema', {}).get('type', 'unknown')
            
            # Check for development-related names
            if any(keyword in field_name for keyword in ['development', 'dev', 'pull', 'pr', 'github', 'git', 'branch', 'commit']):
                dev_candidates.append({
                    'name': field['name'],
                    'id': field_id,
                    'type': field_type
                })
                print(f"📋 Found: {field['name']} (ID: {field_id}, Type: {field_type})")
        
        # Also check for any fields that might be hidden/system fields
        system_candidates = []
        for field in fields:
            field_name = field.get('name', '')
            field_id = field.get('id', '')
            field_type = field.get('schema', {}).get('type', 'unknown')
            
            # Look for system fields that might contain development data
            if (not field_name or 
                field_type in ['any', 'option', 'array'] or 
                field_id.startswith('customfield_') and 'dev' in field_name.lower()):
                system_candidates.append({
                    'name': field_name or 'Unknown',
                    'id': field_id,
                    'type': field_type
                })
        
        print(f"\n🔍 Found {len(dev_candidates)} development-related fields")
        print(f"🔍 Found {len(system_candidates)} potential system fields")
        
        if dev_candidates:
            return dev_candidates[0]['id']
        
        # If no direct matches, let's try to fetch the issue and see what fields actually contain data
        print("\n🔎 No obvious development fields found, checking issue data...")
        return self._find_development_field_by_content()
    
    def _find_development_field_by_content(self) -> str:
        """Try to find development field by examining issue content"""
        # Get the issue with all fields
        issue_url = f"{self.jira_url}/rest/api/3/issue/PDW-9468"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        response = requests.get(issue_url, headers=headers)
        if response.status_code == 200:
            issue_data = response.json()
            fields = issue_data.get('fields', {})
            
            print("🔍 Examining all fields in the issue for development-related content...")
            
            for field_id, field_value in fields.items():
                if field_value is not None:
                    field_str = str(field_value).lower()
                    
                    # Look for GitHub URLs, PR references, or development keywords
                    if any(keyword in field_str for keyword in [
                        'github.com', 'pull', 'pr', 'branch', 'commit', 
                        'dbus/pull', 'ConsumerAffairs/dbus'
                    ]):
                        print(f"🎯 Found potential development content in field {field_id}")
                        print(f"   Content preview: {str(field_value)[:200]}...")
                        return field_id
            
            print("❌ No fields found containing obvious development content")
        
        return None
    
    def _extract_text_content(self, field_content) -> str:
        """Extract plain text from various Jira field formats"""
        if not field_content:
            return "No content provided"
        
        # Handle string content
        if isinstance(field_content, str):
            return field_content
        
        # Handle Atlassian Document Format (ADF)
        if isinstance(field_content, dict):
            if 'content' in field_content:
                return self._extract_adf_text(field_content)
            else:
                return str(field_content)
        
        # Handle other types
        return str(field_content)
    
    def _extract_adf_text(self, adf_content) -> str:
        """Extract text from Atlassian Document Format"""
        text_parts = []
        
        def extract_text_recursive(node):
            if isinstance(node, dict):
                # Extract text from text nodes
                if node.get('type') == 'text':
                    text_parts.append(node.get('text', ''))
                
                # Process content array
                if 'content' in node:
                    for child in node['content']:
                        extract_text_recursive(child)
                        
                # Add line breaks for paragraphs
                if node.get('type') == 'paragraph':
                    text_parts.append('\n')
            
            elif isinstance(node, list):
                for item in node:
                    extract_text_recursive(item)
        
        extract_text_recursive(adf_content)
        
        # Join and clean up the text
        text = ''.join(text_parts).strip()
        # Remove excessive newlines
        text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
        
        return text if text else "No content provided"
    
    def fetch_tickets_with_criteria(self, jql: str) -> List[Dict[str, Any]]:
        """Fetch tickets with description and acceptance criteria"""
        # Find acceptance criteria field
        ac_field_id = self.find_acceptance_criteria_field()
        
        # Define fields to fetch
        fields = ["key", "summary", "description", "status", "assignee", "created", "updated", "parent"]
        
        # Add custom description field if specified
        description_field_id = os.getenv('DESCRIPTION_FIELD')
        if description_field_id and description_field_id not in fields:
            fields.append(description_field_id)
        
        # Add acceptance criteria field
        if ac_field_id and ac_field_id not in fields:
            fields.append(ac_field_id)
        
        # Add all custom fields to see what's available (for debugging)
        all_fields = self.get_field_info()
        custom_fields = [f['id'] for f in all_fields if f['id'].startswith('customfield_')]
        fields.extend(custom_fields[:10])  # Add first 10 custom fields for inspection
        
        # Search for tickets
        results = self.search_tickets(jql, fields)
        
        if not results:
            return []
        
        tickets = []
        for issue in results.get('issues', []):
            # Extract description from custom field if specified, otherwise use standard description
            description_field_id = os.getenv('DESCRIPTION_FIELD', 'description')
            description_field = issue['fields'].get(description_field_id)
            description = self._extract_text_content(description_field)
            
            # Get acceptance criteria if field exists
            acceptance_criteria = None
            if ac_field_id and ac_field_id in issue['fields']:
                ac_content = issue['fields'][ac_field_id]
                acceptance_criteria = self._extract_text_content(ac_content)
            
            ticket_data = {
                'key': issue['key'],
                'summary': issue['fields'].get('summary', 'No summary'),
                'description': description,
                'status': issue['fields'].get('status', {}).get('name', 'Unknown'),
                'acceptance_criteria': acceptance_criteria,
                'assignee': issue['fields']['assignee']['displayName'] if issue['fields'].get('assignee') else None,
                'created': issue['fields'].get('created', ''),
                'updated': issue['fields'].get('updated', '')
            }
            
            # Fetch parent ticket context if feature flag is enabled
            fetch_parent = os.getenv('FETCH_PARENT_CONTEXT', 'false').lower() == 'true'
            if fetch_parent and issue['fields'].get('parent'):
                parent_key = issue['fields']['parent']['key']
                print(f"🔗 Fetching parent ticket context for {parent_key}")
                parent_context = self.fetch_parent_ticket_context(parent_key)
                if parent_context:
                    ticket_data['parent_ticket'] = parent_context
            
            # Fetch PR information using GitHub API search
            pr_info = self.fetch_prs_from_github(issue['key'])
            if pr_info:
                ticket_data['pull_requests'] = pr_info
            
            tickets.append(ticket_data)
        
        return tickets
    
    def print_tickets(self, tickets: List[Dict[str, Any]]):
        """Print tickets in a readable format"""
        print(f"✅ Tickets found: {len(tickets)}")
        
        for ticket in tickets:
            print(f"\n📋 Issue: {ticket['key']}")
            print(f"📝 Summary: {ticket['summary']}")
            print(f"📄 Description:")
            
            description = ticket['description'] or 'No description provided'
            # Format the description with proper markdown styling
            formatted_description = self._format_description(description)
            print(formatted_description)
            
            # Display PR information if available
            if 'pull_requests' in ticket and ticket['pull_requests']:
                prs = ticket['pull_requests']
                print(f"\n📋 Pull Requests ({len(prs)}):")
                for repo, pr in prs.items():
                    print(f"  Repository: {repo}")
                    print(f"  - PR #{pr.get('number')}: {pr.get('title')}")
                    print(f"    State: {pr.get('state')} | Author: {pr.get('author')}")
                    print(f"    URL: {pr.get('url')}")
                    if pr.get('body'):
                        body_preview = pr['body'][:100] + '...' if len(pr['body']) > 100 else pr['body']
                        print(f"    Description: {body_preview}")
                    
                    # Display code changes summary if available
                    if pr.get('code_changes'):
                        changes = pr['code_changes']
                        print(f"    📁 Code Changes: {changes['total_files']} files")
                        print(f"       +{changes['summary']['additions']} -{changes['summary']['deletions']} lines")
                        
                        # Show top 3 files changed
                        files = changes.get('files', [])[:3]
                        for file_info in files:
                            print(f"       • {file_info['filename']} ({file_info['status']}) +{file_info['additions']} -{file_info['deletions']}")
                        
                        if len(changes.get('files', [])) > 3:
                            print(f"       ... and {len(changes['files']) - 3} more files")
                    
                    print()
            else:
                print(f"\n🔗 Pull Requests: No PRs found")
            
            # Display parent ticket information if available
            if 'parent_ticket' in ticket and ticket['parent_ticket']:
                parent = ticket['parent_ticket']
                print(f"\n📋 Parent Ticket: {parent['key']} - {parent['summary']}")
                if parent.get('description'):
                    parent_desc_preview = parent['description'][:200] + '...' if len(parent['description']) > 200 else parent['description']
                    print(f"    Description: {parent_desc_preview}")
                if parent.get('acceptance_criteria'):
                    parent_ac_preview = parent['acceptance_criteria'][:100] + '...' if len(parent['acceptance_criteria']) > 100 else parent['acceptance_criteria']
                    print(f"    Acceptance Criteria: {parent_ac_preview}")
                
                # Display related issues if available
                if parent.get('related_issues'):
                    related_issues = parent['related_issues']
                    print(f"\n🔗 Child Issues ({len(related_issues)}):")
                    for issue in related_issues:
                        print(f"    • {issue['key']} - {issue['summary']}")
                        print(f"      Status: {issue['status']}")
            
            print("=" * 60)
            if ticket['acceptance_criteria']:
                print("✅ Acceptance Criteria:")
                ac_formatted = self._format_acceptance_criteria(ticket['acceptance_criteria'])
                print(ac_formatted)
            else:
                print("✅ Acceptance Criteria: Not found or not set")
    
    def _format_description(self, description: str) -> str:
        """Format description with proper markdown styling"""
        if description == 'No description provided':
            return description
        
        # Replace section headers with markdown formatting
        formatted = description.replace('WHAT:', '**WHAT:**')
        formatted = formatted.replace('WHY:', '\n**WHY:**')
        formatted = formatted.replace('Story/Task details', '\n### Story/Task details')
        formatted = formatted.replace('Business', '**Business**')
        formatted = formatted.replace('QA', '\n**QA**')
        formatted = formatted.replace('Admin', '\n**Admin**')
        formatted = formatted.replace('Code Summary', '\n**Code Summary**')
        formatted = formatted.replace('Additional Context', '\n**Additional Context**')
        
        # Add bullet points for lists
        lines = formatted.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith('Creating a new') or line.startswith('Registering it') or line.startswith('Refactoring the base') or line.startswith('A partial refactor') or line.startswith('This task focuses') or line.startswith('This addresses'):
                line = f"• {line}"
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def _format_acceptance_criteria(self, criteria: str) -> str:
        """Format acceptance criteria with bullet points"""
        if not criteria:
            return "Not found or not set"
        
        # Split by lines and add bullet points
        lines = criteria.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('•') and not line.startswith('-'):
                line = f"• {line}"
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def generate_test_cases(self, ticket_data: Dict[str, Any], pr_context: str = "", parent_context: str = "", confluence_context: str = "") -> tuple[str | None, str]:
        """Generate test cases using Claude AI based on ticket data"""
        issue_key = ticket_data.get('key', 'Unknown')
        summary = ticket_data.get('summary', 'No summary')
        description = ticket_data.get('description', 'No description')
        acceptance_criteria = ticket_data.get('acceptance_criteria', 'No acceptance criteria')
        
        print(f"🤖 Using Claude AI to generate test cases based on comprehensive context...")
        
        # Create comprehensive context for test case generation
        context = f"""TICKET: {issue_key}
SUMMARY: {summary}

DESCRIPTION:
{description}

ACCEPTANCE CRITERIA:
{acceptance_criteria}"""
        
        if pr_context:
            context += pr_context
            print(f"📋 Including enhanced context ({len(pr_context)} characters)")
        
        if parent_context:
            context += parent_context
            print(f"📋 Including parent ticket context ({len(parent_context)} characters)")
        
        if confluence_context:
            context += confluence_context
            print(f"📋 Including project documentation context ({len(confluence_context)} characters)")
        
        # Add comments and attachments context if available
        comments_context = self._build_comments_context(ticket_data)
        if comments_context:
            context += comments_context
            print(f"📋 Including comments context ({len(comments_context)} characters)")
        
        attachments_context = self._build_attachments_context(ticket_data)
        if attachments_context:
            context += attachments_context
            print(f"📋 Including attachments context ({len(attachments_context)} characters)")
        
        # Store the context that will be used for test case generation
        generation_context = context
        
        # Generate test cases using Claude AI with all the context
        prompt = f"""You are a QA expert generating comprehensive test cases for a software development ticket to be executed in our QA environment.
Be comprehensive and precise. Output only the test cases in the specified format.

IMPORTANT: Generate test cases ONLY for the main ticket described in the TICKET, SUMMARY, DESCRIPTION, and ACCEPTANCE CRITERIA sections. 

The PARENT TICKET CONTEXT, CHILD ISSUES CONTEXT, and PROJECT DOCUMENTATION CONTEXT sections are provided for broader project understanding and context awareness, but should NOT be the primary focus of your test cases. Use this context to:
- Better understand the bigger picture and business goals
- Ensure test cases align with the overall project direction
- Include relevant integration points where they relate to the main ticket
- Avoid conflicts with parallel work streams
- Understand the broader project architecture and requirements

PRIMARY TEST FOCUS: Generate test cases specifically for the main ticket's functionality, implementation, and acceptance criteria.

Based on the following context, generate detailed, specific test cases that cover:
1. Implementation verification based on actual code changes
2. Acceptance criteria validation  
3. Developer-provided test guidance from PR descriptions
4. Regression testing for existing functionality
5. Edge cases and error scenarios
6. Integration testing

Context:
{context}

Generate test cases in this format:

### Test Case 1 – Verify Task Deletes Sessions Older Than 30 Days (dtc)

**Steps:**

1. Connect to the **dtc** application environment.
2. Open Django shell:

   ```bash
   python manage.py shell
   ```
3. Insert test records into `django_session`:

   * Some sessions with `expire_date` > 30 days ago.
   * Some sessions within the last 30 days.
4. Import and run cleanup task:

   ```python
   from app.common.tasks import cleanup_django_sessions
   cleanup_django_sessions()
   ```
5. Query `django_session` table after execution:

   ```sql
   SELECT COUNT(*) FROM django_session;
   ```

**Expected:**

* Sessions older than 30 days are **deleted**.
* Recent sessions remain intact.

---

### Test Case 2 – Verify Task Logs Properly When No Sessions To Delete (dtc)

**Steps:**

1. Ensure all sessions in **dtc** are recent (within 30 days).
2. Run the cleanup task manually (same steps as above).
3. Check logs or console output.

**Expected:**

* Log states **“No expired sessions found”**.
* Task exits without error.

---

### Test Case 3 – Verify Task Scheduled in Celery Beat (dtc)

**Steps:**

1. Open Django Admin for **dtc**:

   ```
   https://mainsite-01.qa.consumeraffairs.com/admin/django_celery_beat/periodictask/
   ```
2. Find task named:
   **`cleanup_django_sessions`** or similar.
3. Validate:

   * Enabled.
   * Cron schedule: `0 0 * * *` (**runs daily at 12:00 AM**).
   * Timezone: `US/Central`.

**Expected:**

* Task is scheduled correctly for daily execution.






QA Environment Requirements:
- All test cases will be performed in our QA environment
- Use Django admin interface to check data if possible
- Use Django shell if indicated in the PR description or code changes
- Access APIs through proper authentication and endpoints
- We don't have to run the migrations in the QA environment, it will be automatically done by the application

QA Environment Base URLs (use these in test cases):
- STYLEGUIDE_URL = "https://qa-styleguide.consumeraffairs.com"
- MAINSITE_URL = "https://mainsite-01.qa.consumeraffairs.com"
- SB_URL = "https://my-01.qa.consumeraffairs.com"
- LEADS_API_BASE_URL = "https://leads-api-01.qa.consumeraffairs.com"
- TOOLS_URL = "https://qa-tools.consumeraffairs.com"
- COMMHUB_URL = "http://qa-commhub.consumeraffairs.com"
- DBUS_URL = "https://dbus-01.qa.consumeraffairs.com"
- DTC_BASE_URL = "https://qa-dtc.consumeraffairs.com"
- AUTH_URL = "https://accounts-01.qa.consumeraffairs.com"
- REVIEWS_API_BASE_URL = "https://reviews-api-01.qa.consumeraffairs.com"
- MATCH_API_BASE_URL = "https://match-api-01.qa.consumeraffairs.com"
- USERDB_ENDPOINT_URL = "https://userdb-01.qa.consumeraffairs.com"
- BRANDS_APP_FRONTEND_URL = "https://qa-aspect.consumeraffairs.com"
- BRANDS_API_BASE_URL = "https://brands-api-01.qa.consumeraffairs.com"

Repository to Application Mapping:
- leads-api → LEADS_API_BASE_URL (https://leads-api-01.qa.consumeraffairs.com)
- dbus → DBUS_URL (https://dbus-01.qa.consumeraffairs.com)  
- ConsumerAffairs → MAINSITE_URL (https://mainsite-01.qa.consumeraffairs.com/) [Mainsite]
- silverback → SB_URL (https://my-01.qa.consumeraffairs.com) [Silverback]
- dtc → DTC_BASE_URL (https://qa-dtc.consumeraffairs.com)
- reviews-api → REVIEWS_API_BASE_URL (https://reviews-api-01.qa.consumeraffairs.com)
- match-api → MATCH_API_BASE_URL (https://match-api-01.qa.consumeraffairs.com)
- brandsapp-redesign → BRANDS_API_BASE_URL (https://brands-api-01.qa.consumeraffairs.com) [Backend]
- brandsapp-redesign-nextjs → BRANDS_APP_FRONTEND_URL (https://qa-aspect.consumeraffairs.com/) [Frontend]
- userdb → USERDB_ENDPOINT_URL (https://userdb-01.qa.consumeraffairs.com)
- commhub → COMMHUB_URL (http://qa-commhub.consumeraffairs.com)
- tools → TOOLS_URL (https://qa-tools.consumeraffairs.com)
- auth → AUTH_URL (https://accounts-01.qa.consumeraffairs.com)

Requirements:
- ALWAYS incorporate developer testing guidance from PR descriptions (look for any sections containing "Test")
- Try to group test cases into test steps when possible and very related to each other
- Convert developer-provided test steps into actionable QA test cases with exact commands
- Include specific shell commands, imports, or code snippets that developers specified
- AUTOMATICALLY identify the correct QA environment URL based on the repository name from PR context using the mapping above
- Provide CLEAR, EXECUTABLE steps with:
  * Exact URLs to navigate to using the QA base URLs provided above based on repository mapping
  * For UI testing: Use frontend URLs (e.g., "Navigate to https://qa-aspect.consumeraffairs.com/" for brandsapp-redesign-nextjs)
  * For API testing: Use API endpoints (e.g., "POST to https://leads-api-01.qa.consumeraffairs.com/api/v1/validate" for leads-api)
  * For Django admin: Use admin interfaces (e.g., "Navigate to https://mainsite-01.qa.consumeraffairs.com/admin/" for ConsumerAffairs repo)
  * Specific buttons/links to click (e.g., "Click the 'Submit' button")
  * Exact commands to run in Django shell (e.g., "from app.common.tasks import cleanup_django_sessions")
  * Where to look for results (e.g., "Check application logs", "Verify in Django admin interface")
  * Use the appropriate QA base URL for ALL types of testing (UI, API, admin) based on the repository identified from the PR context
  * Keep FrontEnd and Backend Test Cases separate
- Be specific to the actual implementation details provided in the code changes
- Include both positive and negative test scenarios  
- Reference specific class names, methods, or components from the code changes
- Make every step actionable for QA environment constraints
- Specify expected log messages, Django admin changes, or UI feedback
- If testing APIs, include exact endpoints, headers, and payload examples suitable for QA environment
- Try to build the test cases like a QA engineer would do
- Try to make them easy to understand for Product Owners
- If an endpoint, method, or behavior isn’t visible in code/PR/AC, label it Assumption: and keep it minimal.
- Detect the repo name from PR context (title, branch, or changed file paths) and prefix all links/requests with the mapped QA base URL. If multiple repos are touched, create separate sections per repo.
- verify coverage (all ACs referenced at least once; each changed function referenced by at least one test).Not to print the self-check, only use it to improve the final.

IMPORTANT: Generate ONLY the test cases without any introductory text or concluding summary. Start directly with the first test case heading and end with the last test case. Do not include phrases like "Based on the provided context" at the beginning or "These test cases cover..." at the end.

Generate comprehensive, QA environment-appropriate test cases now:"""

        # Call external AI generation script with the context
        print(f"🔄 Generating test cases with Claude AI...")
        print(f"📝 Context length: {len(context)} characters")
        
        try:
            # Initialize Claude client
            client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            
            # Generate test cases using Claude
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            test_cases = response.content[0].text
            print(f"✅ Successfully generated {len(test_cases)} characters of test cases")
            
            return test_cases, generation_context
            
        except Exception as e:
            error_msg = f"Error setting up AI generation: {str(e)}"
            print(f"⚠️ AI generation setup failed: {str(e)}")
            return None, generation_context
    
    def _convert_markdown_to_adf(self, content: str) -> list:
        """Convert markdown-like content to ADF format for Jira rich text fields"""
        blocks = []
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                # Empty line - add a paragraph break
                i += 1
                continue
                
            if line.startswith('### '):
                # H3 header
                blocks.append({
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [{"type": "text", "text": line[4:]}]
                })
            elif line.startswith('## '):
                # H2 header
                blocks.append({
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": line[3:]}]
                })
            elif line.startswith('# '):
                # H1 header
                blocks.append({
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": line[2:]}]
                })
            elif line.startswith('**') and line.endswith('**'):
                # Bold text as paragraph
                blocks.append({
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": line[2:-2],
                        "marks": [{"type": "strong"}]
                    }]
                })
            elif line.startswith('```'):
                # Code block
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                
                if code_lines:
                    blocks.append({
                        "type": "codeBlock",
                        "attrs": {"language": "bash"},
                        "content": [{"type": "text", "text": '\n'.join(code_lines)}]
                    })
            elif line.startswith('- ') or line.startswith('* '):
                # Bullet list
                list_items = []
                while i < len(lines) and (lines[i].strip().startswith('- ') or lines[i].strip().startswith('* ')):
                    item_text = lines[i].strip()[2:]
                    list_items.append({
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": item_text}]
                        }]
                    })
                    i += 1
                i -= 1  # Adjust for the outer loop increment
                
                if list_items:
                    blocks.append({
                        "type": "bulletList",
                        "content": list_items
                    })
            elif line.startswith('---'):
                # Horizontal rule
                blocks.append({"type": "rule"})
            else:
                # Regular paragraph
                if line:
                    blocks.append({
                        "type": "paragraph",
                        "content": [{"type": "text", "text": line}]
                    })
            
            i += 1
        
        return blocks if blocks else [{
            "type": "paragraph",
            "content": [{"type": "text", "text": content}]
        }]
    
    def update_jira_field(self, issue_key: str, field_id: str, content: str) -> bool:
        """Update a Jira field with content"""
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Create ADF (Atlassian Document Format) structure for rich text fields
        # Parse markdown-like content and convert to proper ADF format
        content_blocks = self._convert_markdown_to_adf(content)
        
        adf_content = {
            "type": "doc",
            "version": 1,
            "content": content_blocks
        }
        
        payload = {
            "fields": {
                field_id: adf_content
            }
        }
        
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code == 204:
            print(f"✅ Successfully updated {field_id} for {issue_key}")
            return True
        else:
            print(f"❌ Error updating {field_id} for {issue_key}: {response.status_code} - {response.text}")
            return False
    
    def process_tickets_with_test_cases(self, jql: str) -> List[Dict[str, Any]]:
        """Fetch tickets and generate test cases for each"""
        tickets = self.fetch_tickets_with_criteria(jql)
        
        if not tickets:
            return []
        
        # Fetch all mentioned Confluence documentation for broader project context
        fetch_confluence = os.getenv('FETCH_CONFLUENCE', 'false').lower() == 'true'
        confluence_docs = {}
        confluence_mentions = {}
        
        if fetch_confluence:
            confluence_docs = self.fetch_all_mentioned_documentation(tickets)
            confluence_mentions = self.find_confluence_mentions_for_tickets(tickets)
        else:
            print("ℹ️  Confluence fetching disabled (FETCH_CONFLUENCE=false)")
        
        # Fetch Jira comments and attachments for main tickets
        fetch_comments = os.getenv('FETCH_COMMENTS_JIRA', 'false').lower() == 'true'
        fetch_attachments = os.getenv('FETCH_ATTACHMENTS_JIRA', 'false').lower() == 'true'
        
        if fetch_comments or fetch_attachments:
            print(f"🔗 Fetching additional Jira data...")
            for ticket in tickets:
                ticket_key = ticket['key']
                
                if fetch_comments:
                    print(f"💬 Fetching comments for {ticket_key}...")
                    ticket['comments'] = self.fetch_jira_comments(ticket_key)
                else:
                    print("ℹ️  Jira comments fetching disabled (FETCH_COMMENTS_JIRA=false)")
                
                if fetch_attachments:
                    print(f"📎 Fetching attachments for {ticket_key}...")
                    ticket['attachments'] = self.fetch_jira_attachments(ticket_key)
                else:
                    print("ℹ️  Jira attachments fetching disabled (FETCH_ATTACHMENTS_JIRA=false)")
        else:
            print("ℹ️  Jira comments and attachments fetching disabled")
        
        test_cases_field_id = os.getenv('TEST_CASES_FIELD', 'customfield_11600')
        
        for ticket in tickets:
            print(f"\n🔄 Processing {ticket['key']}...")
            
            # Fetch PR information using GitHub API search
            print(f"🔗 Fetching PR info for {ticket['key']}...")
            pr_info = self.fetch_prs_from_github(ticket['key'])
            
            if pr_info:
                # Fetch code changes for each PR
                for repo, pr in pr_info.items():
                    code_changes = self.fetch_pr_code_changes(pr['url'])
                    if 'error' not in code_changes:
                        pr['code_changes'] = code_changes
                    else:
                        pr['code_changes'] = None
                
                ticket['pull_requests'] = pr_info
                print(f"📋 Found {len(pr_info)} PR(s) across repositories")
                for repo, pr in pr_info.items():
                    print(f"  - {repo}: PR #{pr['number']} ({pr['state']})")
                    if pr.get('code_changes'):
                        changes = pr['code_changes']['summary']
                        print(f"    Code changes: {pr['code_changes']['total_files']} files, +{changes['additions']} -{changes['deletions']}")
            else:
                print(f"  No PR information found")
                ticket['pull_requests'] = {}
            
            # Generate test cases (include PR information if available)
            pr_context = ""
            if pr_info:
                pr_context_parts = []
                for repo, pr in pr_info.items():
                    if pr.get('body') or pr.get('code_changes'):
                        context_part = f"\n\nPULL REQUEST CONTEXT FROM {repo} - PR #{pr['number']}:\nTitle: {pr['title']}\nState: {pr['state']}\nAuthor: {pr['author']}"
                        
                        if pr.get('body'):
                            context_part += f"\nDescription:\n{pr['body']}"
                        
                        # Add code changes if available
                        if pr.get('code_changes'):
                            code_context = self.format_code_changes_for_context(pr['code_changes'])
                            if code_context:
                                context_part += f"\n{code_context}"
                        
                        pr_context_parts.append(context_part)
                
                if pr_context_parts:
                    pr_context = ''.join(pr_context_parts)
                    print(f"📋 Including PR context from {len(pr_context_parts)} repository/repositories for test case generation")
            
            # Build parent context if available
            parent_context = ""
            if ticket.get('parent_ticket'):
                parent = ticket['parent_ticket']
                parent_context = f"\n\nPARENT TICKET CONTEXT:\nKey: {parent['key']}\nSummary: {parent['summary']}\nDescription: {parent['description']}"
                if parent.get('acceptance_criteria'):
                    parent_context += f"\nAcceptance Criteria: {parent['acceptance_criteria']}"
                
                # Add child issues context if available
                if parent.get('related_issues'):
                    related_issues = parent['related_issues']
                    parent_context += f"\n\nCHILD ISSUES CONTEXT (for broader project understanding, not primary test focus):"
                    for issue in related_issues:
                        parent_context += f"\n\n{issue['key']} - {issue['summary']}"
                        parent_context += f"\nStatus: {issue['status']}"
                        if issue.get('description'):
                            # Truncate long descriptions
                            desc = issue['description'][:300] + "..." if len(issue['description']) > 300 else issue['description']
                            parent_context += f"\nDescription: {desc}"
                        if issue.get('acceptance_criteria'):
                            # Truncate long acceptance criteria
                            ac = issue['acceptance_criteria'][:200] + "..." if len(issue['acceptance_criteria']) > 200 else issue['acceptance_criteria']
                            parent_context += f"\nAcceptance Criteria: {ac}"
            
            # Build Confluence documentation context
            confluence_context = ""
            if confluence_docs:
                confluence_context = "\n\nPROJECT DOCUMENTATION CONTEXT:"
                for page_id, doc in confluence_docs.items():
                    confluence_context += f"\n\n--- {doc['title']} ---"
                    confluence_context += f"\nURL: {doc['url']}"
                    if doc.get('body'):
                        # Limit each document to reasonable length
                        body = doc['body'][:2000] + "..." if len(doc['body']) > 2000 else doc['body']
                        confluence_context += f"\nContent:\n{body}"
            
            # Build Confluence mentions context - include ALL related tickets (main, parent, siblings)
            if confluence_mentions:
                mention_context = ""
                
                # Get all relevant keys: main ticket, parent, and all sibling issues
                relevant_keys = [ticket['key']]  # Main ticket
                if 'parent_ticket' in ticket:
                    relevant_keys.append(ticket['parent_ticket']['key'])  # Parent ticket
                    
                    # Add all sibling issues (child issues of the parent)
                    if 'related_issues' in ticket['parent_ticket']:
                        for related in ticket['parent_ticket']['related_issues']:
                            sibling_key = related.get('key')
                            if sibling_key and sibling_key not in relevant_keys:
                                relevant_keys.append(sibling_key)
                
                # Process mentions for all relevant keys
                found_mentions = {}
                for key in relevant_keys:
                    if key in confluence_mentions:
                        found_mentions[key] = confluence_mentions[key]
                
                if found_mentions:
                    mention_context = "\n\nCONFLUENCE MENTIONS CONTEXT:"
                    
                    for key, mentions in found_mentions.items():
                        mention_context += f"\n\n--- Pages mentioning {key} ---"
                        for mention in mentions:
                            mention_context += f"\n• {mention['title']} ({mention['space_name']})"
                            mention_context += f"\n  URL: {mention['url']}"
                            if mention.get('body'):
                                # Include relevant excerpt
                                body_excerpt = mention['body'][:800] + "..." if len(mention['body']) > 800 else mention['body']
                                mention_context += f"\n  Content: {body_excerpt}"
                
                confluence_context += mention_context
            
            test_cases, generation_context = self.generate_test_cases(ticket, pr_context=pr_context, parent_context=parent_context, confluence_context=confluence_context)
            
            if test_cases:
                print(f"📝 Generated test cases for {ticket['key']}")
                
                # Add the context used for test case generation to the ticket data
                ticket['test_case_generation_context'] = generation_context
                
                # Update Jira field
                success = self.update_jira_field(ticket['key'], test_cases_field_id, test_cases)
                
                if success:
                    ticket['test_cases'] = test_cases
                    ticket['test_cases_updated'] = True
                else:
                    ticket['test_cases_updated'] = False
            else:
                print(f"❌ Failed to generate test cases for {ticket['key']}")
                ticket['test_cases_updated'] = False
            
            # Add Confluence documentation to the ticket data
            if confluence_docs:
                ticket['mentioned_documentation'] = confluence_docs
            
            # Add Confluence mentions to the ticket data - include ALL related tickets
            if confluence_mentions:
                # Filter mentions for all related tickets (main, parent, siblings)
                ticket_mentions = {}
                relevant_keys = [ticket['key']]  # Main ticket
                if 'parent_ticket' in ticket:
                    relevant_keys.append(ticket['parent_ticket']['key'])  # Parent ticket
                    
                    # Add all sibling issues
                    if 'related_issues' in ticket['parent_ticket']:
                        for related in ticket['parent_ticket']['related_issues']:
                            sibling_key = related.get('key')
                            if sibling_key and sibling_key not in relevant_keys:
                                relevant_keys.append(sibling_key)
                
                # Collect mentions for all relevant keys
                for key in relevant_keys:
                    if key in confluence_mentions:
                        ticket_mentions[key] = confluence_mentions[key]
                
                if ticket_mentions:
                    ticket['confluence_mentions'] = ticket_mentions
        
        return tickets
    
    def fetch_parent_ticket_context(self, parent_key: str) -> Dict[str, Any]:
        """Fetch parent ticket with description and acceptance criteria fields"""
        if not parent_key:
            return {}
        
        # Get the same custom fields we use for regular tickets
        description_field_id = os.getenv('DESCRIPTION_FIELD', 'description')
        ac_field_id = os.getenv('ACCEPTANCE_CRITERIA_FIELD')
        
        fields = ["key", "summary", description_field_id]
        if ac_field_id:
            fields.append(ac_field_id)
        
        url = f"{self.jira_url}/rest/api/3/issue/{parent_key}"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        params = {
            "fields": ",".join(fields)
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                issue_data = response.json()
                fields_data = issue_data.get('fields', {})
                
                # Extract description from custom field
                description_content = fields_data.get(description_field_id)
                description = self._extract_text_content(description_content)
                
                # Extract acceptance criteria if available
                acceptance_criteria = None
                if ac_field_id and ac_field_id in fields_data:
                    ac_content = fields_data[ac_field_id]
                    acceptance_criteria = self._extract_text_content(ac_content)
                
                parent_data = {
                    'key': parent_key,
                    'summary': fields_data.get('summary', 'No summary'),
                    'description': description,
                    'acceptance_criteria': acceptance_criteria
                }
                
                # Fetch linked issues if feature flag is enabled
                fetch_parent = os.getenv('FETCH_PARENT_CONTEXT', 'false').lower() == 'true'
                if fetch_parent:
                    linked_issues = self.fetch_linked_issues(parent_key)
                    if linked_issues:
                        parent_data['related_issues'] = linked_issues
                        print(f"   🔗 Included {len(linked_issues)} related issues")
                
                return parent_data
            else:
                print(f"⚠️ Error fetching parent ticket {parent_key}: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"⚠️ Error fetching parent ticket {parent_key}: {str(e)}")
            return {}
    
    def fetch_linked_issues(self, parent_key: str) -> List[Dict[str, Any]]:
        """Fetch child issues of the parent ticket using JQL search"""
        if not parent_key:
            return []
        
        # Use JQL to find all child issues of the parent
        jql_query = f'parent = {parent_key}'
        
        # Get the same custom fields we use for regular tickets
        description_field_id = os.getenv('DESCRIPTION_FIELD', 'description')
        ac_field_id = os.getenv('ACCEPTANCE_CRITERIA_FIELD')
        
        fields = ["key", "summary", "status", description_field_id]
        if ac_field_id:
            fields.append(ac_field_id)
        
        try:
            # Use the existing search_tickets method to find child issues
            search_results = self.search_tickets(jql_query, fields)
            
            if not search_results or 'issues' not in search_results:
                return []
            
            child_issues = search_results['issues']
            if not child_issues:
                return []
            
            linked_issues = []
            print(f"🔗 Found {len(child_issues)} child issues for parent {parent_key}")
            
            for issue in child_issues:
                # Extract fields similar to fetch_tickets_with_criteria
                fields_data = issue.get('fields', {})
                
                # Extract description from custom field or standard field  
                description_content = fields_data.get(description_field_id)
                description = self._extract_text_content(description_content)
                
                # Extract acceptance criteria if available
                acceptance_criteria = None
                if ac_field_id and ac_field_id in fields_data:
                    ac_content = fields_data[ac_field_id]
                    acceptance_criteria = self._extract_text_content(ac_content)
                
                issue_data = {
                    'key': issue['key'],
                    'summary': fields_data.get('summary', 'No summary'),
                    'status': fields_data.get('status', {}).get('name', 'Unknown'),
                    'description': description,
                    'acceptance_criteria': acceptance_criteria,
                    'relationship': 'child of'  # All are child issues
                }
                
                linked_issues.append(issue_data)
                print(f"   ✅ Fetched {issue['key']} (child issue)")
            
            return linked_issues
            
        except Exception as e:
            print(f"⚠️ Error fetching child issues for {parent_key}: {str(e)}")
            return []
    
    def _fetch_issue_details(self, issue_key: str, fields: List[str]) -> Dict[str, Any]:
        """Fetch detailed information for a specific issue"""
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        params = {
            "fields": ",".join(fields)
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                issue_data = response.json()
                fields_data = issue_data.get('fields', {})
                
                # Get custom fields
                description_field_id = os.getenv('DESCRIPTION_FIELD', 'description')
                ac_field_id = os.getenv('ACCEPTANCE_CRITERIA_FIELD')
                
                # Extract description from custom field or standard field
                description_content = fields_data.get(description_field_id)
                description = self._extract_text_content(description_content)
                
                # Extract acceptance criteria if available
                acceptance_criteria = None
                if ac_field_id and ac_field_id in fields_data:
                    ac_content = fields_data[ac_field_id]
                    acceptance_criteria = self._extract_text_content(ac_content)
                
                return {
                    'key': issue_key,
                    'summary': fields_data.get('summary', 'No summary'),
                    'status': fields_data.get('status', {}).get('name', 'Unknown'),
                    'description': description,
                    'acceptance_criteria': acceptance_criteria
                }
            else:
                print(f"   ⚠️ Error fetching {issue_key}: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"   ⚠️ Error fetching {issue_key}: {str(e)}")
            return {}
    
    def get_issue_links(self, issue_key: str) -> List[Dict[str, Any]]:
        """Get all links for a Jira issue including PR links"""
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        # Request specific fields including issuelinks
        params = {
            "fields": "issuelinks,remotelinks"
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            issue_data = response.json()
            links = []
            
            # Process issue links (internal Jira links)
            for link in issue_data.get('fields', {}).get('issuelinks', []):
                if 'outwardIssue' in link:
                    links.append({
                        'type': 'issue_link',
                        'relationship': link.get('type', {}).get('outward', 'related to'),
                        'key': link['outwardIssue']['key'],
                        'summary': link['outwardIssue']['fields']['summary'],
                        'status': link['outwardIssue']['fields']['status']['name']
                    })
                elif 'inwardIssue' in link:
                    links.append({
                        'type': 'issue_link', 
                        'relationship': link.get('type', {}).get('inward', 'related to'),
                        'key': link['inwardIssue']['key'],
                        'summary': link['inwardIssue']['fields']['summary'],
                        'status': link['inwardIssue']['fields']['status']['name']
                    })
            
            return links
        else:
            print(f"Error fetching links for {issue_key}: {response.status_code} - {response.text}")
            return []
    
    def fetch_prs_from_github(self, issue_key: str) -> Dict[str, Dict[str, Any]]:
        """Fetch PRs from GitHub using search API by ticket key in title"""
        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            print(f"⚠️ GITHUB_TOKEN not found in environment variables")
            return {}
        
        # GitHub search API endpoint
        search_url = "https://api.github.com/search/issues"
        
        # Search query: find PRs with the ticket key in title
        query = f"{issue_key} in:title type:pr"
        
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Jira-Ticket-Fetcher'
        }
        
        params = {
            'q': query
        }
        
        try:
            print(f"🔍 Searching GitHub for PRs with '{issue_key}' in title...")
            response = requests.get(search_url, headers=headers, params=params)
            
            if response.status_code == 200:
                search_data = response.json()
                items = search_data.get('items', [])
                
                if not items:
                    print(f"   No PRs found for {issue_key}")
                    return {}
                
                print(f"   Found {len(items)} PR(s) for {issue_key}")
                
                # Group PRs by repository
                repos_prs = {}
                for item in items:
                    repo_full_name = item.get('repository_url', '').replace('https://api.github.com/repos/', '')
                    if not repo_full_name:
                        continue
                    
                    pr_data = {
                        'number': item.get('number'),
                        'title': item.get('title'),
                        'url': item.get('html_url'),
                        'state': item.get('state'),
                        'author': item.get('user', {}).get('login'),
                        'created_at': item.get('created_at'),
                        'updated_at': item.get('updated_at'),
                        'body': item.get('body', ''),
                        'repository': repo_full_name
                    }
                    
                    if repo_full_name not in repos_prs:
                        repos_prs[repo_full_name] = []
                    repos_prs[repo_full_name].append(pr_data)
                
                # For each repository, keep only the PR with lowest ID that is not declined
                selected_prs = {}
                for repo, prs in repos_prs.items():
                    # Sort by PR number (ascending) to get lowest ID first
                    sorted_prs = sorted(prs, key=lambda x: x.get('number', 0))
                    
                    for pr in sorted_prs:
                        # Skip declined PRs (closed without being merged)
                        if pr.get('state') == 'closed':
                            # We need to check if it was merged by fetching detailed PR info
                            detailed_pr = self._get_detailed_pr_info(pr['url'])
                            if detailed_pr and not detailed_pr.get('merged_at'):
                                print(f"   Skipping declined PR #{pr['number']} in {repo}")
                                continue
                        
                        # This is the lowest ID non-declined PR for this repo
                        selected_prs[repo] = pr
                        print(f"   Selected PR #{pr['number']} from {repo} (state: {pr['state']})")
                        break
                
                return selected_prs
                
            elif response.status_code == 403:
                print(f"❌ GitHub API rate limited or access denied")
                return {}
            else:
                print(f"❌ GitHub search API error: {response.status_code} - {response.text[:200]}")
                return {}
                
        except Exception as e:
            print(f"❌ Error searching GitHub for PRs: {str(e)}")
            return {}
    
    def _get_detailed_pr_info(self, pr_url: str) -> Dict[str, Any]:
        """Get detailed PR info to check if it was merged"""
        import re
        
        # Extract owner, repo, and PR number from URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
        if not match:
            return {}
        
        owner, repo, pr_number = match.groups()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        
        github_token = os.getenv('GITHUB_TOKEN')
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Jira-Ticket-Fetcher'
        }
        
        try:
            response = requests.get(api_url, headers=headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"   Error fetching detailed PR info: {str(e)}")
        
        return {}
    
    def fetch_pr_code_changes(self, pr_url: str) -> Dict[str, Any]:
        """Fetch code changes (diff) from GitHub PR"""
        import re
        
        # Extract owner, repo, and PR number from URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
        if not match:
            return {'error': 'Invalid GitHub PR URL format'}
        
        owner, repo, pr_number = match.groups()
        
        # GitHub API endpoint for PR files
        files_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        
        github_token = os.getenv('GITHUB_TOKEN')
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Jira-Ticket-Fetcher'
        }
        
        if github_token:
            headers['Authorization'] = f'token {github_token}'
        
        try:
            print(f"🔍 Fetching code changes for PR #{pr_number}...")
            response = requests.get(files_url, headers=headers)
            
            if response.status_code == 200:
                files_data = response.json()
                
                code_changes = {
                    'total_files': len(files_data),
                    'files': [],
                    'summary': {
                        'additions': 0,
                        'deletions': 0,
                        'changes': 0
                    }
                }
                
                for file_data in files_data:
                    file_info = {
                        'filename': file_data.get('filename'),
                        'status': file_data.get('status'),  # added, modified, deleted, renamed
                        'additions': file_data.get('additions', 0),
                        'deletions': file_data.get('deletions', 0),
                        'changes': file_data.get('changes', 0),
                        'patch': file_data.get('patch', ''),  # The actual code diff
                        'blob_url': file_data.get('blob_url'),
                        'raw_url': file_data.get('raw_url')
                    }
                    
                    # Update totals
                    code_changes['summary']['additions'] += file_info['additions']
                    code_changes['summary']['deletions'] += file_info['deletions']
                    code_changes['summary']['changes'] += file_info['changes']
                    
                    code_changes['files'].append(file_info)
                
                print(f"   ✅ Found {code_changes['total_files']} files, +{code_changes['summary']['additions']} -{code_changes['summary']['deletions']} lines")
                return code_changes
                
            elif response.status_code == 404:
                print(f"   ❌ PR files not found")
                return {'error': 'PR files not found', 'status_code': 404}
            elif response.status_code == 403:
                print(f"   ❌ Rate limited or access denied for PR files")
                return {'error': 'Access denied or rate limited', 'status_code': 403}
            else:
                print(f"   ❌ GitHub API error: {response.status_code}")
                return {'error': f'GitHub API error: {response.status_code}'}
                
        except Exception as e:
            print(f"   ❌ Error fetching PR code changes: {str(e)}")
            return {'error': str(e)}
    
    def format_code_changes_for_context(self, code_changes: Dict[str, Any], max_length: int = 8000) -> str:
        """Format code changes for inclusion in test case generation context"""
        if 'error' in code_changes or not code_changes.get('files'):
            return ""
        
        context = f"""
CODE CHANGES SUMMARY:
- Files changed: {code_changes['total_files']}
- Additions: +{code_changes['summary']['additions']} lines
- Deletions: -{code_changes['summary']['deletions']} lines
- Total changes: {code_changes['summary']['changes']} lines

DETAILED FILE CHANGES:
"""
        
        current_length = len(context)
        
        for file_info in code_changes['files']:
            file_header = f"""
📁 {file_info['filename']} ({file_info['status']})
   +{file_info['additions']} -{file_info['deletions']} changes

"""
            
            # Check if we have space for this file
            if current_length + len(file_header) > max_length:
                context += f"\n... (truncated - remaining files not shown)"
                break
            
            context += file_header
            current_length += len(file_header)
            
            # Add patch/diff if it fits
            patch = file_info.get('patch', '')
            if patch:
                # Limit patch size to avoid overwhelming the context
                max_patch_length = min(2000, max_length - current_length - 100)
                if len(patch) > max_patch_length:
                    patch = patch[:max_patch_length] + "\n... (truncated)"
                
                patch_section = f"```diff\n{patch}\n```\n"
                
                if current_length + len(patch_section) <= max_length:
                    context += patch_section
                    current_length += len(patch_section)
                else:
                    context += "```\n(Code diff too large to include)\n```\n"
                    break
        
        return context

    def extract_mentioned_on_links(self, content: str) -> List[str]:
        """Extract Confluence page URLs from 'mentioned on' sections in Jira content"""
        if not content:
            return []
        
        # Pattern to match Confluence URLs in various formats
        confluence_patterns = [
            # Direct Confluence URLs
            r'https://[^/]+\.atlassian\.net/wiki/spaces/[^/]+/pages/[^/\s]+/[^\s<>"]+',
            # URLs in href attributes
            r'href="(https://[^/]+\.atlassian\.net/wiki/spaces/[^/]+/pages/[^/\s"]+/[^"\s]+)"',
            # URLs in markdown links
            r'\[.*?\]\((https://[^/]+\.atlassian\.net/wiki/spaces/[^/]+/pages/[^/\s)]+/[^)\s]+)\)',
        ]
        
        mentioned_links = []
        for pattern in confluence_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if isinstance(matches[0] if matches else None, tuple):
                # For patterns with groups, extract the URL group
                mentioned_links.extend([match[0] if isinstance(match, tuple) else match for match in matches])
            else:
                mentioned_links.extend(matches)
        
        # Remove duplicates and decode URL-encoded characters
        unique_links = []
        for link in mentioned_links:
            decoded_link = requests.utils.unquote(link)
            if decoded_link not in unique_links:
                unique_links.append(decoded_link)
        
        return unique_links

    def get_confluence_page_id_from_url(self, url: str) -> Optional[str]:
        """Extract page ID from Confluence URL"""
        # Pattern: /pages/{pageId}/PageTitle
        page_id_match = re.search(r'/pages/(\d+)/', url)
        if page_id_match:
            return page_id_match.group(1)
        return None

    def fetch_confluence_content(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Fetch Confluence page content using REST API v2"""
        try:
            # Get base Confluence URL from Jira URL
            confluence_base = self.jira_url.replace('//consumeraffairs.atlassian.net', '//consumeraffairs.atlassian.net')
            
            url = f"{confluence_base}/wiki/api/v2/pages/{page_id}"
            headers = {
                "Authorization": self.auth_header,
                "Accept": "application/json"
            }
            
            # Add body format parameter to get the content
            params = {"body-format": "atlas_doc_format"}
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                page_data = response.json()
                
                # Extract meaningful content
                content_info = {
                    "id": page_data.get("id"),
                    "title": page_data.get("title", ""),
                    "body": "",
                    "url": f"{confluence_base}/wiki/spaces/{page_data.get('spaceId', '')}/pages/{page_id}"
                }
                
                # Extract body content if available
                if "body" in page_data and "atlas_doc_format" in page_data["body"]:
                    body_content = page_data["body"]["atlas_doc_format"].get("value", "")
                    # Convert ADF to readable text
                    content_info["body"] = self._extract_confluence_text(body_content)
                
                return content_info
            else:
                print(f"❌ Failed to fetch Confluence page {page_id}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error fetching Confluence page {page_id}: {str(e)}")
            return None

    def _extract_confluence_text(self, adf_content: str) -> str:
        """Extract readable text from Confluence ADF content"""
        try:
            if isinstance(adf_content, str):
                adf_data = json.loads(adf_content)
            else:
                adf_data = adf_content
            
            # Use existing ADF text extraction method
            return self._extract_adf_text(adf_data)
        except:
            # If JSON parsing fails, return as-is
            return str(adf_content) if adf_content else ""

    def fetch_all_mentioned_documentation(self, tickets: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Fetch all Confluence documentation mentioned across all tickets"""
        print("🔗 Fetching mentioned documentation...")
        
        all_confluence_content = {}
        processed_pages = set()  # Avoid fetching the same page multiple times
        
        for ticket in tickets:
            # Check main ticket content (both custom and standard description fields)
            ticket_content = f"{ticket.get('description', '')} {ticket.get('summary', '')}"
            
            # Check parent ticket if exists
            if 'parent_ticket' in ticket:
                parent = ticket['parent_ticket']
                # Check parent ticket content
                parent_desc = parent.get('description', '')
                ticket_content += f" {parent_desc} {parent.get('summary', '')}"
                
                # Check related issues
                if 'related_issues' in parent:
                    for related in parent['related_issues']:
                        ticket_content += f" {related.get('description', '')} {related.get('summary', '')}"
            
            # Extract Confluence links
            mentioned_links = self.extract_mentioned_on_links(ticket_content)
            
            for link in mentioned_links:
                page_id = self.get_confluence_page_id_from_url(link)
                if page_id and page_id not in processed_pages:
                    print(f"   📄 Fetching Confluence page: {page_id}")
                    content = self.fetch_confluence_content(page_id)
                    if content:
                        all_confluence_content[page_id] = content
                        processed_pages.add(page_id)
        
        if all_confluence_content:
            print(f"   ✅ Fetched {len(all_confluence_content)} Confluence document(s)")
        else:
            print("   ℹ️  No Confluence documents found in mentioned links")
        
        return all_confluence_content

    def fetch_confluence_page_storage(self, page_id: str) -> Optional[str]:
        """Fetch Confluence page storage format to analyze Jira macros"""
        try:
            confluence_base = self.jira_url.replace('//consumeraffairs.atlassian.net', '//consumeraffairs.atlassian.net')
            
            # Use the storage format endpoint to get raw content with Jira macros
            url = f"{confluence_base}/wiki/rest/api/content/{page_id}?expand=body.storage"
            headers = {
                "Authorization": self.auth_header,
                "Accept": "application/json"
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                page_data = response.json()
                storage_body = page_data.get("body", {}).get("storage", {}).get("value", "")
                return storage_body
            else:
                print(f"   ❌ Failed to fetch storage for page {page_id}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"   ❌ Error fetching storage for page {page_id}: {str(e)}")
            return None

    def extract_jira_tickets_from_storage(self, storage_content: str) -> List[str]:
        """Extract Jira ticket keys from Confluence storage format"""
        if not storage_content:
            return []
        
        ticket_keys = []
        
        # Pattern 1: Jira structured macros - <ac:structured-macro ac:name="jira"
        jira_macro_pattern = r'<ac:structured-macro ac:name="jira"[^>]*>.*?</ac:structured-macro>'
        jira_macros = re.findall(jira_macro_pattern, storage_content, re.DOTALL)
        
        for macro in jira_macros:
            # Extract ticket key from macro parameters
            # Look for patterns like <ac:parameter ac:name="key">PDW-8744</ac:parameter>
            key_pattern = r'<ac:parameter ac:name="key">([^<]+)</ac:parameter>'
            keys = re.findall(key_pattern, macro)
            ticket_keys.extend(keys)
        
        # Pattern 2: Smart links with Jira URLs
        smart_link_pattern = r'data-card-url="https://[^"]*\.atlassian\.net/browse/([^"]+)"'
        smart_link_keys = re.findall(smart_link_pattern, storage_content)
        ticket_keys.extend(smart_link_keys)
        
        # Pattern 3: Direct href links to Jira
        href_pattern = r'href="https://[^"]*\.atlassian\.net/browse/([^"]+)"'
        href_keys = re.findall(href_pattern, storage_content)
        ticket_keys.extend(href_keys)
        
        # Pattern 4: Plain text ticket references (PDW-XXXX format)
        plain_text_pattern = r'\b(PDW-\d+)\b'
        plain_keys = re.findall(plain_text_pattern, storage_content)
        ticket_keys.extend(plain_keys)
        
        # Remove duplicates and return
        return list(set(ticket_keys))

    def search_known_confluence_pages_for_tickets(self, ticket_keys: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Search known Confluence pages by examining their storage format"""
        print("🔍 Searching known Confluence pages via storage format...")
        
        mentions_found = {}
        
        # Get a list of pages that might contain project documentation
        # We'll search for pages with project-related terms first
        project_search_terms = [
            "Project Plan", "Email Campaign", "Aspect", "Development", 
            "Epic", "Feature", "Implementation"
        ]
        
        confluence_base = self.jira_url.replace('//consumeraffairs.atlassian.net', '//consumeraffairs.atlassian.net')
        search_url = f"{confluence_base}/wiki/rest/api/search"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        # Find potentially relevant pages
        candidate_pages = []
        for search_term in project_search_terms:
            search_params = {
                "cql": f'title ~ "{search_term}" AND type = page',
                "limit": 10,
                "expand": "content.space,content.version"
            }
            
            response = requests.get(search_url, headers=headers, params=search_params)
            
            if response.status_code == 200:
                results = response.json().get("results", [])
                for result in results:
                    content = result.get("content", {})
                    page_id = content.get("id")
                    if page_id:
                        candidate_pages.append({
                            "id": page_id,
                            "title": content.get("title", ""),
                            "space_name": content.get("space", {}).get("name", ""),
                            "space_key": content.get("space", {}).get("key", "")
                        })
        
        # Remove duplicates
        seen_pages = set()
        unique_pages = []
        for page in candidate_pages:
            if page["id"] not in seen_pages:
                unique_pages.append(page)
                seen_pages.add(page["id"])
        
        print(f"   📄 Analyzing {len(unique_pages)} candidate pages for Jira references...")
        
        # Analyze each candidate page
        for page in unique_pages:
            storage_content = self.fetch_confluence_page_storage(page["id"])
            if storage_content:
                found_tickets = self.extract_jira_tickets_from_storage(storage_content)
                
                # Check if any of our target tickets are mentioned
                relevant_tickets = [ticket for ticket in found_tickets if ticket in ticket_keys]
                
                if relevant_tickets:
                    print(f"   ✅ Found tickets {relevant_tickets} in '{page['title']}'")
                    
                    for ticket_key in relevant_tickets:
                        if ticket_key not in mentions_found:
                            mentions_found[ticket_key] = []
                        
                        mention_info = {
                            "id": page["id"],
                            "title": page["title"],
                            "type": "page",
                            "space_key": page["space_key"],
                            "space_name": page["space_name"],
                            "url": f"{confluence_base}/wiki/spaces/{page['space_key']}/pages/{page['id']}",
                            "excerpt": f"Found via storage format analysis in {page['title']}",
                            "lastModified": "",
                            "body": storage_content[:1500] + "..." if len(storage_content) > 1500 else storage_content
                        }
                        
                        mentions_found[ticket_key].append(mention_info)
        
        return mentions_found

    def search_confluence_for_ticket_mentions(self, ticket_keys: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Search Confluence for mentions of ticket keys using search API"""
        print(f"🔍 Searching Confluence for mentions of tickets: {', '.join(ticket_keys)}")
        
        confluence_base = self.jira_url.replace('//consumeraffairs.atlassian.net', '//consumeraffairs.atlassian.net')
        mentions_found = {}
        
        for ticket_key in ticket_keys:
            try:
                # Use Confluence search API to find pages mentioning the ticket key
                search_url = f"{confluence_base}/wiki/api/v2/pages"
                headers = {
                    "Authorization": self.auth_header,
                    "Accept": "application/json"
                }
                
                # Search for pages containing the ticket key
                params = {
                    "body-format": "atlas_doc_format",
                    "limit": 10  # Limit to avoid too many results
                }
                
                # Use the search endpoint with CQL (Confluence Query Language)
                search_url = f"{confluence_base}/wiki/rest/api/search"
                
                # Use precise CQL queries to avoid false positives
                cql_queries = [
                    f'text ~ "{ticket_key}" AND type = page',  # Full ticket key (PDW-8744)
                    f'title ~ "{ticket_key}" AND type = page',  # Search in titles
                    f'text ~ "browse/{ticket_key}" AND type = page',  # URL pattern in smart links
                    f'text ~ "atlassian.net/browse/{ticket_key}" AND type = page',  # Full URL pattern
                    f'text ~ "{ticket_key}:" AND type = page',  # Title pattern (PDW-8744: Title)
                ]
                
                # Only search for ticket numbers if they're part of a clear ticket pattern
                # This avoids false positives like addresses or random numbers
                if ticket_key.startswith('PDW-'):
                    ticket_number = ticket_key.replace('PDW-', '')
                    # Only add number search if it's a reasonable length to avoid false positives
                    if len(ticket_number) >= 4:  # Only search for 4+ digit numbers to avoid false matches
                        cql_queries.extend([
                            f'text ~ "PDW-{ticket_number}" AND type = page',  # Ensure PDW- prefix
                            f'text ~ "browse/PDW-{ticket_number}" AND type = page',  # URL with PDW prefix
                        ])
                
                # Try each CQL query and combine results
                all_results = []
                found_page_ids = set()  # Track to avoid duplicates
                successful_queries = []  # Track which queries worked
                
                for i, cql_query in enumerate(cql_queries):
                    search_params = {
                        "cql": cql_query,
                        "limit": 15,
                        "expand": "content.space,content.version,content.body.view"
                    }
                    
                    response = requests.get(search_url, headers=headers, params=search_params)
                    
                    if response.status_code == 200:
                        search_results = response.json()
                        results = search_results.get("results", [])
                        
                        # Add unique results
                        new_results_count = 0
                        for result in results:
                            page_id = result.get("content", {}).get("id")
                            if page_id and page_id not in found_page_ids:
                                all_results.append(result)
                                found_page_ids.add(page_id)
                                new_results_count += 1
                        
                        if new_results_count > 0:
                            successful_queries.append(f"Query {i+1}: '{cql_query}' -> {new_results_count} results")
                    else:
                        continue  # Try next query if this one fails
                
                # Print debug info for successful searches
                if successful_queries:
                    print(f"   🔍 Search details for {ticket_key}:")
                    for query_info in successful_queries:
                        print(f"      {query_info}")
                
                # Process results if we found any
                ticket_mentions = []
                if all_results:
                    for result in all_results:
                        content = result.get("content", {})
                        if content:
                            mention_info = {
                                "id": content.get("id"),
                                "title": content.get("title", ""),
                                "type": content.get("type", ""),
                                "space_key": content.get("space", {}).get("key", ""),
                                "space_name": content.get("space", {}).get("name", ""),
                                "url": f"{confluence_base}/wiki{content.get('_links', {}).get('webui', '')}" if content.get('_links', {}).get('webui') else "",
                                "excerpt": result.get("excerpt", ""),
                                "lastModified": content.get("version", {}).get("when", "")
                            }
                            
                            # Try to get the page content for more context and validation
                            if mention_info["id"]:
                                page_content = self.fetch_confluence_content(mention_info["id"])
                                if page_content:
                                    full_body = page_content["body"]
                                    
                                    # Validate this is a real ticket mention, not a false positive
                                    if self._is_valid_ticket_mention(ticket_key, full_body, mention_info["title"]):
                                        mention_info["body"] = full_body[:1500] + "..." if len(full_body) > 1500 else full_body
                                        ticket_mentions.append(mention_info)
                                    else:
                                        continue  # Skip false positives
                                else:
                                    # If we can't get content, still check title and excerpt
                                    excerpt = result.get("excerpt", "")
                                    if self._is_valid_ticket_mention(ticket_key, excerpt, mention_info["title"]):
                                        ticket_mentions.append(mention_info)
                            else:
                                # If no page ID, still check excerpt
                                excerpt = result.get("excerpt", "")
                                if self._is_valid_ticket_mention(ticket_key, excerpt, mention_info["title"]):
                                    ticket_mentions.append(mention_info)

                # Also search using storage format analysis to find smart links and Jira macros
                print(f"   🔍 Also searching with storage format analysis for {ticket_key}...")
                storage_results = self.search_known_confluence_pages_for_tickets([ticket_key])
                if storage_results.get(ticket_key):
                    print(f"   ✅ Storage format analysis found {len(storage_results[ticket_key])} additional mentions")
                    
                    # Merge storage results with existing mentions, avoiding duplicates
                    existing_page_ids = {mention.get("id") for mention in ticket_mentions if mention.get("id")}
                    for storage_mention in storage_results[ticket_key]:
                        if storage_mention.get("id") not in existing_page_ids:
                            ticket_mentions.append(storage_mention)
                
                if ticket_mentions:
                    mentions_found[ticket_key] = ticket_mentions
                    print(f"   ✅ Found {len(ticket_mentions)} Confluence page(s) mentioning {ticket_key} (including storage format analysis)")
                else:
                    print(f"   ℹ️  No Confluence mentions found for {ticket_key}")
                    
            except Exception as e:
                print(f"   ❌ Exception searching for {ticket_key}: {str(e)}")
        
        return mentions_found

    def _is_valid_ticket_mention(self, ticket_key: str, content: str, title: str) -> bool:
        """Validate if this is a real ticket mention, not a false positive"""
        if not content and not title:
            return False
        
        search_text = f"{content} {title}".lower()
        ticket_lower = ticket_key.lower()
        
        # Check for obvious false positives
        false_positive_indicators = [
            "address", "street", "blvd", "boulevard", "avenue", "road", "drive",
            "phone", "telephone", "zip", "postal", "credit card", "account number",
            "transaction", "order", "invoice", "receipt", "serial number"
        ]
        
        for indicator in false_positive_indicators:
            if indicator in search_text and ticket_key.replace('PDW-', '') in search_text:
                return False
        
        # Positive indicators - content that suggests real ticket mentions
        positive_indicators = [
            ticket_lower,  # Full ticket key
            f"browse/{ticket_lower}",  # Jira URL
            f"{ticket_lower}:",  # Ticket title format
            "jira", "atlassian", "ticket", "issue", "story", "epic",
            "project", "development", "feature", "bug", "task"
        ]
        
        # Must have at least one positive indicator
        has_positive = any(indicator in search_text for indicator in positive_indicators)
        
        # Additional validation for PDW tickets
        if ticket_key.startswith('PDW-'):
            # If only the number was found (not full PDW-XXXX), be more strict
            ticket_number = ticket_key.replace('PDW-', '')
            if ticket_number in search_text and ticket_lower not in search_text:
                # Only accept if it's in a clear project/development context
                development_context = [
                    "pdw", "project", "development", "jira", "ticket", "issue", 
                    "story", "epic", "task", "feature", "improvement"
                ]
                return any(ctx in search_text for ctx in development_context)
        
        return has_positive

    def find_confluence_mentions_for_tickets(self, tickets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Find Confluence mentions for main ticket and parent ticket only"""
        ticket_keys_to_search = set()
        
        # Collect only main ticket and parent ticket keys
        for ticket in tickets:
            # Add main ticket key
            ticket_keys_to_search.add(ticket['key'])
            
            # Add parent ticket key if exists
            if 'parent_ticket' in ticket:
                parent_key = ticket['parent_ticket'].get('key')
                if parent_key:
                    ticket_keys_to_search.add(parent_key)
        
        # Convert to list and search
        ticket_keys_list = list(ticket_keys_to_search)
        print(f"🔍 Confluence search limited to main ticket and parent only: {', '.join(ticket_keys_list)}")
        return self.search_confluence_for_ticket_mentions(ticket_keys_list)

    def fetch_jira_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        """Fetch comments for a Jira issue"""
        try:
            url = f"{self.jira_url}/rest/api/3/issue/{issue_key}/comment"
            headers = {
                "Authorization": self.auth_header,
                "Accept": "application/json"
            }
            
            params = {
                "maxResults": 50,  # Limit to 50 most recent comments
                "orderBy": "created",  # Order by creation date
                "expand": "renderedBody"  # Get rendered HTML content
            }
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                comments_data = response.json()
                comments = []
                
                for comment in comments_data.get("comments", []):
                    comment_info = {
                        "id": comment.get("id"),
                        "author": comment.get("author", {}).get("displayName", "Unknown"),
                        "author_email": comment.get("author", {}).get("emailAddress", ""),
                        "created": comment.get("created", ""),
                        "updated": comment.get("updated", ""),
                        "body": comment.get("body", {}),
                        "rendered_body": comment.get("renderedBody", "")
                    }
                    
                    # Extract plain text from comment body
                    if comment_info["body"]:
                        comment_info["body_text"] = self._extract_adf_text(comment_info["body"])
                    else:
                        comment_info["body_text"] = ""
                    
                    comments.append(comment_info)
                
                print(f"   ✅ Found {len(comments)} comment(s) for {issue_key}")
                return comments
            else:
                print(f"   ❌ Failed to fetch comments for {issue_key}: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"   ❌ Error fetching comments for {issue_key}: {str(e)}")
            return []

    def fetch_jira_attachments(self, issue_key: str) -> List[Dict[str, Any]]:
        """Fetch attachments for a Jira issue"""
        try:
            url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
            headers = {
                "Authorization": self.auth_header,
                "Accept": "application/json"
            }
            
            params = {
                "fields": "attachment"
            }
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                issue_data = response.json()
                attachments_data = issue_data.get("fields", {}).get("attachment", [])
                attachments = []
                
                for attachment in attachments_data:
                    attachment_info = {
                        "id": attachment.get("id"),
                        "filename": attachment.get("filename", ""),
                        "author": attachment.get("author", {}).get("displayName", "Unknown"),
                        "created": attachment.get("created", ""),
                        "size": attachment.get("size", 0),
                        "mime_type": attachment.get("mimeType", ""),
                        "content_url": attachment.get("content", ""),
                        "thumbnail_url": attachment.get("thumbnail", "")
                    }
                    
                    # Format file size for readability
                    size_bytes = attachment_info["size"]
                    if size_bytes < 1024:
                        attachment_info["size_formatted"] = f"{size_bytes} bytes"
                    elif size_bytes < 1024 * 1024:
                        attachment_info["size_formatted"] = f"{size_bytes / 1024:.1f} KB"
                    else:
                        attachment_info["size_formatted"] = f"{size_bytes / (1024 * 1024):.1f} MB"
                    
                    attachments.append(attachment_info)
                
                print(f"   ✅ Found {len(attachments)} attachment(s) for {issue_key}")
                return attachments
            else:
                print(f"   ❌ Failed to fetch attachments for {issue_key}: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"   ❌ Error fetching attachments for {issue_key}: {str(e)}")
            return []

    def _extract_adf_text(self, adf_content: Dict[str, Any]) -> str:
        """Extract plain text from Atlassian Document Format (ADF) content"""
        try:
            if not adf_content:
                return ""
            
            def extract_text_recursive(node):
                text_parts = []
                
                if isinstance(node, dict):
                    # Handle text nodes
                    if node.get("type") == "text":
                        text_parts.append(node.get("text", ""))
                    
                    # Process content array
                    if "content" in node:
                        for child in node["content"]:
                            text_parts.append(extract_text_recursive(child))
                    
                    # Add newlines for paragraph breaks
                    if node.get("type") == "paragraph":
                        text_parts.append("\n")
                
                elif isinstance(node, list):
                    for item in node:
                        text_parts.append(extract_text_recursive(item))
                
                return "".join(text_parts)
            
            return extract_text_recursive(adf_content).strip()
            
        except Exception as e:
            print(f"   ⚠️ Error extracting ADF text: {str(e)}")
            return str(adf_content)[:500] + "..." if len(str(adf_content)) > 500 else str(adf_content)

    def _build_comments_context(self, ticket: Dict[str, Any]) -> str:
        """Build context string from ticket comments"""
        comments = ticket.get('comments', [])
        if not comments:
            return ""
        
        context_parts = ["\n\nJIRA COMMENTS:"]
        context_parts.append("=" * 50)
        
        # Limit to most recent 10 comments to avoid overwhelming context
        recent_comments = comments[-10:] if len(comments) > 10 else comments
        
        for i, comment in enumerate(recent_comments, 1):
            context_parts.append(f"\nComment #{i}:")
            context_parts.append(f"Author: {comment.get('author', 'Unknown')}")
            context_parts.append(f"Created: {comment.get('created', '')}")
            
            body_text = comment.get('body_text', '').strip()
            if body_text:
                # Truncate very long comments
                if len(body_text) > 1000:
                    body_text = body_text[:1000] + "... [truncated]"
                context_parts.append(f"Content: {body_text}")
            context_parts.append("-" * 30)
        
        return "\n".join(context_parts)

    def _build_attachments_context(self, ticket: Dict[str, Any]) -> str:
        """Build context string from ticket attachments"""
        attachments = ticket.get('attachments', [])
        if not attachments:
            return ""
        
        context_parts = ["\n\nJIRA ATTACHMENTS:"]
        context_parts.append("=" * 50)
        
        for i, attachment in enumerate(attachments, 1):
            context_parts.append(f"\nAttachment #{i}:")
            context_parts.append(f"Filename: {attachment.get('filename', 'Unknown')}")
            context_parts.append(f"Size: {attachment.get('size_formatted', 'Unknown')}")
            context_parts.append(f"Type: {attachment.get('mime_type', 'Unknown')}")
            context_parts.append(f"Author: {attachment.get('author', 'Unknown')}")
            context_parts.append(f"Created: {attachment.get('created', '')}")
            context_parts.append("-" * 30)
        
        return "\n".join(context_parts)

def main():
    # Load environment variables from .env file
    from dotenv import load_dotenv
    load_dotenv()
    
    # Get credentials from environment variables
    jira_url = "https://consumeraffairs.atlassian.net"
    email = os.getenv('JIRA_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')
    
    if not email or not api_token:
        print("❌ Error: JIRA_EMAIL and JIRA_API_TOKEN must be set in .env file")
        print("Please check your .env file contains:")
        print("JIRA_EMAIL=your-email@consumeraffairs.com")
        print("JIRA_API_TOKEN=your-jira-api-token")
        return
    
    # Initialize fetcher
    fetcher = JiraTicketFetcher(jira_url, email, api_token)
    
    # Get JQL query from environment variable or user input
    jql_query = os.getenv('JQL_QUERY')
    if not jql_query:
        jql_query = input("Enter your JQL query (or press Enter for default): ").strip()
        if not jql_query:
            jql_query = "project = CA AND status != Done ORDER BY created DESC"
    
    # Check if we're in preview mode
    preview_mode = os.getenv('PREVIEW_MODE', 'false').lower() == 'true'
    
    if preview_mode:
        # Preview mode: just fetch basic ticket info and display
        print("Fetching ticket information...")
        tickets = fetcher.fetch_tickets_with_criteria(jql_query)
        
        if tickets:
            print(f"✅ Found {len(tickets)} ticket(s):")
            print("=" * 60)
            
            for i, ticket in enumerate(tickets, 1):
                print(f"{i}. {ticket['key']} - {ticket['summary']}")
                print(f"   Status: {ticket['status']} | Assignee: {ticket['assignee']}")
                print("")
                
            print("=" * 60)
        else:
            print("❌ No tickets found matching the JQL query.")
            exit(1)
    else:
        # Full mode: process with test case generation
        print(f"Searching for tickets with JQL: {jql_query}")
        
        # Check if we should generate test cases
        generate_test_cases = os.getenv('GENERATE_TEST_CASES', 'false').lower() == 'true'
        
        if generate_test_cases:
            print("🤖 AI test case generation enabled")
            print("Fetching tickets and generating test cases...")
            
            tickets = fetcher.process_tickets_with_test_cases(jql_query)
        else:
            print("Fetching tickets...")
            tickets = fetcher.fetch_tickets_with_criteria(jql_query)
        
        if tickets:
            fetcher.print_tickets(tickets)
            
            # Automatically save to JSON file in non-preview mode
            filename = "jira_tickets.json"
            with open(filename, 'w') as f:
                json.dump(tickets, f, indent=2, default=str)
            print(f"Results automatically saved to {filename}")
        else:
            print("No tickets found or error occurred.")
            exit(1)

if __name__ == "__main__":
    main()