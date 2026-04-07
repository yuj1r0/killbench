"""
Answer Server
Plays all roles in the case (patient, nurse, clinician, etc)
"""
import json


class AnswerServer:
    """
    Responds to doctor's questions in character as various roles.
    NO gate logic - just acts based on what's been unlocked.
    """
    
    def __init__(self, case_data, llm_client):
        self.case = case_data
        self.llm = llm_client
    
    def respond(self, role, question_text, unlocked_gates, unlocked_facts):
        """
        Generate natural response as the specified role.
        
        Args:
            role: "patient", "triage_nurse", "clinician", "lab", "radiology"
            question_text: What the doctor asked/requested
            unlocked_gates: List of gate names that have been opened
            unlocked_facts: List of atomic facts revealed
        
        Returns:
            Natural language response string
        """
        
        # Build context from unlocked information
        available_info = self._build_available_info(unlocked_gates)
        
        # Get character description
        character = self._get_role_description(role)
        
        # Build system prompt
        system_prompt = f"""You are playing the role of: {role}

## CHARACTER:
{character}

## INFORMATION YOU CAN DISCUSS:
{available_info}

## DEFAULT RESPONSES (for questions about things not specifically revealed above):
Physical exam findings not mentioned above:
{json.dumps(self.case['latent_truth'].get('default_normals', {}), indent=2)}

Background information if asked:
{json.dumps(self.case['latent_truth'].get('background_noise', {}), indent=2)}

## CRITICAL RULES:
1. Answer naturally and conversationally as {role}
2. Stay strictly in character
3. ONLY reveal information listed in "INFORMATION YOU CAN DISCUSS" above
4. For questions about unrevealed findings:
   - Use default normals if appropriate
   - Give vague/non-committal answers if defaults don't apply
   - Don't act evasive or suspicious - just answer based on what you know
5. Be concise (1-3 sentences unless more detail is warranted)
6. Be helpful but don't volunteer unrevealed information

## DOCTOR'S QUESTION:
"{question_text}"

## YOUR RESPONSE (as {role}):"""

        # Generate response
        response = self.llm.generate(
            system_prompt=system_prompt,
            user_message="Respond to the doctor's question above. Stay in character. Be natural and concise.",
            temperature=0.4,  # Some natural variation
            max_tokens=500
        )
        
        return response.strip()
    
    def _get_role_description(self, role):
        """Get character traits for the role"""
        
        # Check if role has explicit description in YAML
        if role in self.case.get("roles", {}):
            base_description = self.case["roles"][role]
        else:
            base_description = ""
        
        # Add general role guidelines
        role_guidelines = {
            "patient": """
You are the patient. You are laconic and focused on getting back to work.
You believe muscle relaxants helped you before.
Answer questions honestly but don't volunteer information unless asked.
""",
            "triage_nurse": """
You are a practical, helpful nurse.
You report what you've observed and documented.
You can perform exams and tests if the doctor requests them.
""",
            "clinician": """
You are performing physical examinations for the doctor.
Report findings objectively and accurately.
You are skilled and can perform any standard physical exam maneuver requested.

IMPORTANT: Report only the objective physical exam findings without any meta-evaluative commentary.
DO NOT add interpretive statements like "this is concerning," "this warrants further evaluation,"
or "this suggests [diagnosis]." Let the requesting physician draw their own conclusions from your findings.
""",
            "lab": """
You are the lab technician reporting test results.
Provide results clearly and professionally.
""",
            "radiology": """
You are the radiologist or radiology tech reporting imaging findings.
Provide clear, accurate descriptions of imaging results.
"""
        }
        
        guideline = role_guidelines.get(role, "You are a professional healthcare worker.")
        
        return f"{base_description}\n\n{guideline}"
    
    def _build_available_info(self, unlocked_gates):
        """Build the information that can be discussed based on unlocked gates"""
        info_lines = []
        
        # Add surface-level info (always available)
        info_lines.append("SURFACE LEVEL INFO (always known):")
        if "triage_nurse" in self.case.get("roles", {}):
            info_lines.append(f"Initial presentation: {self.case['roles']['triage_nurse'][:200]}...")
        
        # Add unlocked gate information
        if unlocked_gates:
            info_lines.append("\nUNLOCKED FINDINGS (you can discuss these):")
            for gate_name in unlocked_gates:
                gate = self.case["gates"].get(gate_name, {})
                response_data = gate.get("response", {})
                content = response_data.get("content", "")
                
                info_lines.append(f"\n{gate_name}:")
                info_lines.append(f"  {content}")
                
                # Also note what facts were unlocked
                unlocks = gate.get("unlocks", [])
                if unlocks:
                    info_lines.append(f"  Facts: {', '.join(unlocks)}")
        else:
            info_lines.append("\nNo specific findings unlocked yet.")
        
        return "\n".join(info_lines)
