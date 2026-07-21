"""
Run Case - Main Entry Point
Command-line interface for running killbench cases
"""
import os
import json
import yaml
import argparse
from datetime import datetime
from dotenv import load_dotenv
from llm_clients import get_llm_client
from orchestrator import CaseOrchestrator


def main():
    """Main entry point"""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Run killbench medical decision cases')
    parser.add_argument('--case', type=str, help='Path to case YAML file (overrides config.yaml)')
    parser.add_argument('--doctor', type=str, help='Doctor LLM model (e.g., grok-3, claude-sonnet-4)')
    parser.add_argument('--max-turns', type=int, help='Maximum number of turns (overrides config.yaml)')
    args = parser.parse_args()

    # Load environment variables from .env file
    load_dotenv()

    print("\n" + "="*80)
    print("KILLBENCH - Medical Decision Benchmark")
    print("="*80)

    # Load configuration
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Get case path - command-line argument overrides config
    case_path = args.case if args.case else config['case']['path']
    max_turns = args.max_turns if args.max_turns else config['case']['max_turns']

    # Override doctor model if specified
    if args.doctor:
        # Parse format like "grok-3" or "claude-sonnet-4"
        if args.doctor.startswith('grok'):
            config['llms']['doctor']['provider'] = 'grok'
            config['llms']['doctor']['model'] = args.doctor
        elif args.doctor.startswith('claude'):
            config['llms']['doctor']['provider'] = 'claude'
            config['llms']['doctor']['model'] = args.doctor
        elif args.doctor.startswith('gpt'):
            config['llms']['doctor']['provider'] = 'gpt'
            config['llms']['doctor']['model'] = args.doctor
        elif args.doctor.startswith('gemini'):
            config['llms']['doctor']['provider'] = 'gemini'
            config['llms']['doctor']['model'] = args.doctor

    # Initialize LLMs from config
    print("\n[Initializing LLMs...]")
    print(f"  Doctor: {config['llms']['doctor']['provider']} ({config['llms']['doctor']['model']})")
    print(f"  Referee: {config['llms']['referee']['provider']} ({config['llms']['referee']['model']})")
    print(f"  Answer Server: {config['llms']['answer_server']['provider']} ({config['llms']['answer_server']['model']})")

    try:
        doctor_llm = get_llm_client(
            config['llms']['doctor']['provider'],
            config['llms']['doctor']['model']
        )
        referee_llm = get_llm_client(
            config['llms']['referee']['provider'],
            config['llms']['referee']['model']
        )
        answer_llm = get_llm_client(
            config['llms']['answer_server']['provider'],
            config['llms']['answer_server']['model']
        )
    except Exception as e:
        print(f"\n❌ Error initializing LLMs: {e}")
        print("\nMake sure you have set up your .env file with:")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        print("  XAI_API_KEY=xai-...")
        return

    print("✓ LLMs initialized")
    
    # Create orchestrator
    orchestrator = CaseOrchestrator(
        case_yaml_path=case_path,
        doctor_llm=doctor_llm,
        referee_llm=referee_llm,
        answer_llm=answer_llm
    )
    
    # Run the case
    print("\n[Starting case evaluation...]")
    print("Watch the interaction play out below:")

    result = orchestrator.run_case(
        max_turns=max_turns,
        verbose=config['output']['verbose']
    )

    # Generate timestamped output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    case_id = result['case_id']
    doctor_model = config['llms']['doctor']['model'].replace('/', '_').replace('-', '_')

    # Extract case filename without extension
    case_filename = os.path.splitext(os.path.basename(case_path))[0]

    output_filename = f"{timestamp}_{case_filename}_{doctor_model}.json"
    output_dir = config['output'].get('output_dir', 'outputs')

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, output_filename)

    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\n✓ Results saved to {output_file}")
    
    # Print summary
    print("\n" + "="*80)
    print("RUN SUMMARY")
    print("="*80)
    print(f"Case: {result['case_id']}")
    print(f"Status: {result['status']}")
    print(f"Turns: {result['turns']}")
    
    if 'score' in result:
        score = result['score']
        print(f"Decision: {score['disposition']}")
        # V0.0.3: Handle uncertain dispositions
        if score.get('correct') is None:
            print(f"Correct: ? (uncertain - requires human review)")
        else:
            print(f"Correct: {'✓' if score['correct'] else '✗'}")
        # Only print VoI score if it exists (uncertain dispositions may not have it)
        if 'voi_score' in score:
            print(f"VoI Score: {score['voi_score']:.1f}")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
