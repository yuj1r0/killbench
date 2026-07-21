"""
Run Benchmark - Batch Runner
Runs every case in one or more directories through the killbench pipeline,
reusing a single set of LLM clients, and writes per-case JSON plus a summary.
"""
import os
import glob
import json
import yaml
import argparse
import traceback
import concurrent.futures
from datetime import datetime
from dotenv import load_dotenv
from llm_clients import get_llm_client
from orchestrator import CaseOrchestrator


def apply_doctor_override(config, doctor):
    """Route a --doctor model string to the right provider (mirrors run_case)."""
    if doctor.startswith('grok'):
        provider = 'grok'
    elif doctor.startswith('claude'):
        provider = 'claude'
    elif doctor.startswith('gpt'):
        provider = 'gpt'
    elif doctor.startswith('gemini'):
        provider = 'gemini'
    else:
        provider = config['llms']['doctor']['provider']
    config['llms']['doctor']['provider'] = provider
    config['llms']['doctor']['model'] = doctor


def collect_cases(paths):
    """Expand directories/globs/files into a sorted list of case YAML files."""
    cases = []
    for p in paths:
        if os.path.isdir(p):
            cases.extend(glob.glob(os.path.join(p, '*.yaml')))
        elif any(ch in p for ch in '*?['):
            cases.extend(glob.glob(p))
        elif os.path.isfile(p):
            cases.append(p)
    # Deduplicate while preserving a stable sorted order
    return sorted(set(cases))


def main():
    parser = argparse.ArgumentParser(description='Run the killbench benchmark over many cases')
    parser.add_argument('--cases', type=str, nargs='+',
                        default=['cases', 'cases_dev'],
                        help='Directories, globs, or files of cases (default: cases cases_dev)')
    parser.add_argument('--doctor', type=str, help='Doctor LLM model (e.g. gemini-3.5-flash)')
    parser.add_argument('--max-turns', type=int, help='Max turns per case (overrides config.yaml)')
    parser.add_argument('--workers', '-j', type=int, default=4,
                        help='Cases to run concurrently (default 4; cases are independent). '
                             'Use 1 for sequential/verbose output.')
    args = parser.parse_args()

    load_dotenv()

    print("\n" + "=" * 80)
    print("KILLBENCH - Benchmark Batch Runner")
    print("=" * 80)

    # Load configuration
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    max_turns = args.max_turns if args.max_turns else config['case']['max_turns']
    if args.doctor:
        apply_doctor_override(config, args.doctor)

    # Gather cases
    case_files = collect_cases(args.cases)
    if not case_files:
        print(f"\n❌ No case YAML files found in: {args.cases}")
        return

    # Initialize LLMs once for the whole run
    print("\n[Initializing LLMs...]")
    print(f"  Doctor: {config['llms']['doctor']['provider']} ({config['llms']['doctor']['model']})")
    print(f"  Referee: {config['llms']['referee']['provider']} ({config['llms']['referee']['model']})")
    print(f"  Answer Server: {config['llms']['answer_server']['provider']} ({config['llms']['answer_server']['model']})")
    try:
        doctor_llm = get_llm_client(config['llms']['doctor']['provider'], config['llms']['doctor']['model'])
        referee_llm = get_llm_client(config['llms']['referee']['provider'], config['llms']['referee']['model'])
        answer_llm = get_llm_client(config['llms']['answer_server']['provider'], config['llms']['answer_server']['model'])
    except Exception as e:
        print(f"\n❌ Error initializing LLMs: {e}")
        return
    print(f"✓ LLMs initialized")
    print(f"\nRunning {len(case_files)} case(s), max {max_turns} turns each.\n")

    output_dir = config['output'].get('output_dir', 'outputs')
    os.makedirs(output_dir, exist_ok=True)
    doctor_model = config['llms']['doctor']['model'].replace('/', '_').replace('-', '_')
    batch_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Verbose per-turn output only makes sense sequentially; with >1 worker the
    # streams would interleave, so we suppress it and print a line per finished case.
    verbose = config['output']['verbose'] and args.workers <= 1

    def run_one(case_path):
        """Run a single case end-to-end and return its summary row. Cases are
        independent (fresh orchestrator, shared thread-safe LLM clients), so this
        is safe to call concurrently."""
        case_filename = os.path.splitext(os.path.basename(case_path))[0]
        row = {'case_file': case_path}
        try:
            orchestrator = CaseOrchestrator(
                case_yaml_path=case_path,
                doctor_llm=doctor_llm,
                referee_llm=referee_llm,
                answer_llm=answer_llm,
            )
            result = orchestrator.run_case(max_turns=max_turns, verbose=verbose)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = os.path.join(output_dir, f"{timestamp}_{case_filename}_{doctor_model}.json")
            with open(out_file, 'w') as f:
                json.dump(result, f, indent=2)

            score = result.get('score', {})
            row.update({
                'case_id': result.get('case_id'),
                'status': result.get('status'),
                'turns': result.get('turns'),
                'disposition': score.get('disposition'),
                'correct': score.get('correct'),
                'voi_score': score.get('voi_score'),
                'output_file': out_file,
            })
        except Exception as e:
            row.update({'status': 'error', 'error': str(e), '_traceback': traceback.format_exc()})
        return row

    summary_rows = []
    total = len(case_files)
    if args.workers > 1:
        print(f"Running {total} cases with {args.workers} workers...\n")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(run_one, cp): cp for cp in case_files}
            for done, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                row = fut.result()
                summary_rows.append(row)
                cid = (row.get('case_id') or os.path.basename(row['case_file']))[:50]
                if row.get('status') == 'error':
                    print(f"  [{done}/{total}] ❌ ERROR  {cid}\n{row.get('_traceback', '')}")
                else:
                    c = row.get('correct')
                    mark = '✓' if c is True else ('✗' if c is False else '?')
                    print(f"  [{done}/{total}] {mark}  {cid:<50} {row.get('status')}")
    else:
        for i, case_path in enumerate(case_files, 1):
            print("\n" + "#" * 80)
            print(f"# CASE {i}/{total}: {os.path.splitext(os.path.basename(case_path))[0]}")
            print("#" * 80)
            row = run_one(case_path)
            if row.get('status') == 'error':
                print(f"\n❌ Case failed: {row.get('error')}\n{row.get('_traceback', '')}")
            summary_rows.append(row)

    # Stable ordering for the summary (parallel completion order is arbitrary)
    summary_rows.sort(key=lambda r: r['case_file'])
    for r in summary_rows:
        r.pop('_traceback', None)

    # Write a batch summary
    summary = {
        'batch_stamp': batch_stamp,
        'doctor': config['llms']['doctor'],
        'referee': config['llms']['referee'],
        'answer_server': config['llms']['answer_server'],
        'max_turns': max_turns,
        'total_cases': len(case_files),
        'results': summary_rows,
        # Token usage per role, for cost / Pareto-frontier analysis. Doctor
        # tokens isolate the model under test; referee + answer_server are the
        # orchestration overhead.
        'usage': {
            'doctor': {'model': config['llms']['doctor']['model'], **doctor_llm.usage},
            'referee': {'model': config['llms']['referee']['model'], **referee_llm.usage},
            'answer_server': {'model': config['llms']['answer_server']['model'], **answer_llm.usage},
        },
    }
    summary_file = os.path.join(output_dir, f"BATCH_SUMMARY_{batch_stamp}_{doctor_model}.json")
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    # Console summary
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    correct_ct = sum(1 for r in summary_rows if r.get('correct') is True)
    incorrect_ct = sum(1 for r in summary_rows if r.get('correct') is False)
    uncertain_ct = sum(1 for r in summary_rows if r.get('correct') is None and r.get('status') != 'error')
    error_ct = sum(1 for r in summary_rows if r.get('status') == 'error')
    print(f"{'CASE':<45} {'STATUS':<10} {'DECISION':<14} {'CORRECT':<8} {'VoI'}")
    print("-" * 80)
    for r in summary_rows:
        cid = (r.get('case_id') or os.path.basename(r['case_file']))[:44]
        correct = r.get('correct')
        correct_str = '?' if correct is None else ('✓' if correct else '✗')
        voi = r.get('voi_score')
        voi_str = f"{voi:.1f}" if isinstance(voi, (int, float)) else '-'
        print(f"{cid:<45} {str(r.get('status')):<10} {str(r.get('disposition') or '-'):<14} {correct_str:<8} {voi_str}")
    print("-" * 80)
    print(f"Correct: {correct_ct}   Incorrect: {incorrect_ct}   Uncertain: {uncertain_ct}   Errors: {error_ct}   (of {len(case_files)})")
    print(f"\n✓ Batch summary saved to {summary_file}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
