#!/usr/bin/env python3

import json
import argparse
import sys
from datetime import datetime

def load_diagnostic(filepath):
    """Load and parse a diagnostic JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading diagnostic file {filepath}: {e}")
        sys.exit(1)

def compare_modules(left_modules, right_modules):
    """Compare modules between two diagnostic files."""
    left_modules_dict = {m['name']: m for m in left_modules}
    right_modules_dict = {m['name']: m for m in right_modules}
    
    all_module_names = set(left_modules_dict.keys()).union(set(right_modules_dict.keys()))
    
    diff = {
        'added': [],
        'removed': [],
        'changed': [],
        'unchanged': []
    }
    
    for name in all_module_names:
        left = left_modules_dict.get(name)
        right = right_modules_dict.get(name)
        
        if left and not right:
            diff['removed'].append({'name': name, 'module': left})
        elif not left and right:
            diff['added'].append({'name': name, 'module': right})
        elif left and right:
            changes = []
            if left['status'] != right['status']:
                changes.append(f"Status: {left['status']} -> {right['status']}")
            if left['elapsed_seconds'] != right['elapsed_seconds']:
                changes.append(f"Elapsed: {left['elapsed_seconds']}s -> {right['elapsed_seconds']}s")
            if left['artifact'] != right['artifact']:
                if left['artifact'] is None and right['artifact'] is not None:
                    changes.append(f"Artifact: None -> {right['artifact']}")
                elif left['artifact'] is not None and right['artifact'] is None:
                    changes.append(f"Artifact: {left['artifact']} -> None")
                else:
                    changes.append(f"Artifact: {left['artifact']} -> {right['artifact']}")
            
            if left['output'] != right['output']:
                changes.append("Output changed")
            
            if changes:
                diff['changed'].append({
                    'name': name,
                    'left': left,
                    'right': right,
                    'changes': changes
                })
            else:
                diff['unchanged'].append({'name': name, 'module': left})
    
    return diff

def format_diff(diff):
    """Format the diff output for display."""
    output = []
    
    if diff['added']:
        output.append("\n=== ADDED MODULES ===")
        for item in diff['added']:
            output.append(f"+ {item['name']}: {item['module']['status']}")
            if item['module']['artifact']:
                output.append(f"  Artifact: {item['module']['artifact']}")
            if item['module']['output']:
                output.append(f"  Output: {item['module']['output']}")
    
    if diff['removed']:
        output.append("\n=== REMOVED MODULES ===")
        for item in diff['removed']:
            output.append(f"- {item['name']}: {item['module']['status']}")
            if item['module']['artifact']:
                output.append(f"  Artifact: {item['module']['artifact']}")
            if item['module']['output']:
                output.append(f"  Output: {item['module']['output']}")
    
    if diff['changed']:
        output.append("\n=== CHANGED MODULES ===")
        for item in diff['changed']:
            output.append(f"* {item['name']}:")
            for change in item['changes']:
                output.append(f"  - {change}")
    
    if diff['unchanged']:
        output.append("\n=== UNCHANGED MODULES ===")
        for item in diff['unchanged']:
            output.append(f"= {item['name']}: {item['module']['status']}")
    
    return "\n".join(output)

def main():
    parser = argparse.ArgumentParser(description='Compare diagnostic JSON files')
    parser.add_argument('left', help='Left diagnostic JSON file')
    parser.add_argument('right', help='Right diagnostic JSON file')
    
    args = parser.parse_args()
    
    left_diag = load_diagnostic(args.left)
    right_diag = load_diagnostic(args.right)
    
    # Compare top-level stats
    stats_diff = []
    if left_diag['total_modules'] != right_diag['total_modules']:
        stats_diff.append(f"Total modules: {left_diag['total_modules']} -> {right_diag['total_modules']}")
    if left_diag['passed'] != right_diag['passed']:
        stats_diff.append(f"Passed: {left_diag['passed']} -> {right_diag['passed']}")
    if left_diag['failed'] != right_diag['failed']:
        stats_diff.append(f"Failed: {left_diag['failed']} -> {right_diag['failed']}")
    
    # Compare modules
    module_diff = compare_modules(left_diag['modules'], right_diag['modules'])
    
    # Output results
    print(f"Diagnostic Diff: {args.left} vs {args.right}")
    print(f"Left generated: {left_diag['generated_at']}")
    print(f"Right generated: {right_diag['generated_at']}")
    
    if stats_diff:
        print("\n=== STATS CHANGES ===")
        for change in stats_diff:
            print(f"- {change}")
    
    formatted_diff = format_diff(module_diff)
    if formatted_diff:
        print(formatted_diff)
    else:
        print("\nNo differences found.")

if __name__ == '__main__':
    main()
