"""
Gate Referee
Evaluates whether doctor's questions/actions trigger information gates
"""
import json
from datetime import datetime


class GateReferee:
    """
    Uses an LLM to judge if doctor's question should open gates
    """
    
    def __init__(self, case_data, llm_client):
        self.case = case_data
        self.llm = llm_client
        self.decision_log = []
    
    def evaluate_question(self, question_text, already_unlocked_gates):
        """
        Determine if the question triggers any gates.
        
        Returns:
        {
            "gates_triggered": ["gate_name_1", "gate_name_2"],
            "reasoning": "explanation of decision",
            "confidence": 0.95
        }
        """
        
        # Build list of gates that haven't been unlocked yet
        gates_available = {
            name: data for name, data in self.case["gates"].items()
            if name not in already_unlocked_gates
        }
        
        if not gates_available:
            # All gates already unlocked
            return {
                "gates_triggered": [],
                "reasoning": "All gates already unlocked",
                "confidence": 1.0
            }
        
        # Build prompt for referee
        system_prompt = self._build_referee_prompt(gates_available, already_unlocked_gates)
        
        user_message = f"""Doctor's question/request:
"{question_text}"

Evaluate which gates (if any) this should trigger. Return valid JSON only."""
        
        # Get referee decision
        try:
            response_text = self.llm.generate(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.1,  # Low temp for consistency
                max_tokens=8000,  # Very high limit to see full reasoning
                response_format="json",
                enable_thinking=True  # Judge reasons deeply; budget has room for it
            )

            # Strip markdown code fences if present
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]  # Remove ```json
            if response_text.startswith("```"):
                response_text = response_text[3:]  # Remove ```
            if response_text.endswith("```"):
                response_text = response_text[:-3]  # Remove trailing ```
            response_text = response_text.strip()

            result = json.loads(response_text)
            
            # Validate result has required fields
            if "gates_triggered" not in result:
                result["gates_triggered"] = []
            if "reasoning" not in result:
                result["reasoning"] = "No reasoning provided"
            if "confidence" not in result:
                result["confidence"] = 0.5
            
        except json.JSONDecodeError as e:
            # Fallback if JSON parsing fails
            result = {
                "gates_triggered": [],
                "reasoning": f"JSON parsing failed. Error: {str(e)}",
                "confidence": 0.0
            }
        
        # Log decision for auditing
        self.decision_log.append({
            "question": question_text,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        
        return result
    
    def _build_referee_prompt(self, gates_available, already_unlocked):
        """Build the system prompt for the referee"""
        
        gates_formatted = self._format_gates_for_referee(gates_available)
        
        return f"""You are a referee for a medical case simulation. Your job is to determine if a doctor's question or request should trigger any information gates.

## YOUR ROLE:
- Evaluate if the doctor's question matches the intent and specificity of gate triggers
- Be precise but fair: similar phrasings should match the same gate
- Consider both WHAT is asked and HOW SPECIFICALLY it's asked
- Some gates require specific detail (e.g., "compare both arms"); vague questions may trigger different, incomplete gates

## GATES AVAILABLE (not yet unlocked):
{gates_formatted}

## ALREADY UNLOCKED:
{', '.join(already_unlocked) if already_unlocked else 'None'}

## INSTRUCTIONS:
1. Read the doctor's question carefully
2. Check if it matches any gate triggers (semantically, not just exact text)
3. A gate should trigger if the question's INTENT matches, even if worded differently
4. Return a JSON object with:
   - "gates_triggered": array of gate names (empty array if none)
   - "reasoning": brief explanation (1 sentence max, be concise)
   - "confidence": 0.0-1.0

IMPORTANT: Keep your response SHORT. Only the JSON object, nothing else

## EXAMPLES:
- "Please test strength in both arms" → triggers ask_arm_strength_specific
- "Is his arm strong?" → triggers ask_arm_strength_vague
- "Compare bilateral upper extremity motor function" → triggers ask_arm_strength_specific (same intent, different words)
- "Listen to his heart" → triggers nothing (not in gates)

Be strict but reasonable. Multiple ways to ask the same thing should trigger the same gate.

Return ONLY valid JSON, no other text."""
    
    def _format_gates_for_referee(self, gates_dict):
        """Format gates clearly for the referee to evaluate"""
        formatted_lines = []
        
        for gate_name, gate_data in gates_dict.items():
            triggers = gate_data.get("trigger", [])
            gate_type = gate_data.get("response", {}).get("type", "standard")
            
            # Format trigger list
            trigger_str = "\n    - ".join(triggers)
            
            formatted_lines.append(f"""
Gate: {gate_name}
  Type: {gate_type}
  Triggers:
    - {trigger_str}
""")
        
        return "\n".join(formatted_lines)
