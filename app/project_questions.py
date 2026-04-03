from typing import List, Dict

PROJECT_QUESTIONS = [
    {"field": "database", "question": "Which database do you want to use? (sqlite, postgresql, mongodb)", "options": ["sqlite", "postgresql", "mongodb"]},
    {"field": "auth", "question": "Do you need user authentication? (yes/no)", "options": ["yes", "no"]},
    {"field": "auth_type", "question": "If yes, what auth method? (jwt, oauth, session)", "depends_on": {"auth": "yes"}},
    {"field": "api_style", "question": "REST or GraphQL?", "options": ["rest", "graphql"]},
    {"field": "features", "question": "List any specific features (comma separated):", "freeform": True}
]

def get_missing_project_info(user_input: str, collected_info: dict) -> List[Dict]:
    missing = []
    text = user_input.lower()
    for q in PROJECT_QUESTIONS:
        field = q["field"]
        if field in collected_info:
            continue
            
        # Check dependencies
        depends_on = q.get("depends_on")
        if depends_on:
            skip = False
            for dep_field, dep_val in depends_on.items():
                if collected_info.get(dep_field) != dep_val:
                    skip = True
                    break
            if skip:
                continue
                
        # Try to auto-extract from user input if not freeform
        if "options" in q:
            found = None
            for opt in q["options"]:
                if opt in text:
                    found = opt
                    break
            if found:
                collected_info[field] = found
                continue
                
        missing.append(q)
    return missing