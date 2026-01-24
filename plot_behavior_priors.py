"""
Visualize behavioral priors extracted from GitHub Archive data.
Creates histograms and transition graphs from behavioral_priors.json.
"""
import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict

from config import OUTPUT_JSON_PATH, OUTPUT_FIGURES_DIR

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10


def load_behavioral_priors(json_path: str) -> Dict:
    """Load behavioral priors from JSON file."""
    print(f"Loading behavioral priors from {json_path}...")
    with open(json_path, 'r') as f:
        data = json.load(f)
    print(f"✓ Loaded data for {data['metadata']['num_users']:,} users")
    return data


def plot_timing_histogram(data: Dict, output_dir: Path):
    """Plot histogram of inter-event timing deltas."""
    print("\nPlotting timing histogram...")
    
    timing_stats = data['ft_intra_user_timing']['statistics']
    sample_values = data['ft_intra_user_timing']['sample_values']
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    # Linear scale
    ax1.hist(sample_values, bins=50, edgecolor='black', alpha=0.7, color='steelblue')
    ax1.set_xlabel('Time Between Events (seconds)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Inter-Event Timing Distribution (Linear Scale)')
    ax1.axvline(timing_stats['median'], color='red', linestyle='--', 
                label=f"Median: {timing_stats['median']:.2f}s")
    ax1.axvline(timing_stats['mean'], color='orange', linestyle='--', 
                label=f"Mean: {timing_stats['mean']:.2f}s")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Log scale
    log_values = np.log10(np.array(sample_values) + 1)  # +1 to avoid log(0)
    ax2.hist(log_values, bins=50, edgecolor='black', alpha=0.7, color='steelblue')
    ax2.set_xlabel('Log₁₀(Time Between Events + 1)')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Inter-Event Timing Distribution (Log Scale)')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_path = output_dir / "timing_histogram.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_path}")
    plt.close()
    
    # Print statistics
    print("\nTiming Statistics:")
    print(f"  Count: {timing_stats['count']:,}")
    print(f"  Mean: {timing_stats['mean']:.2f}s")
    print(f"  Median: {timing_stats['median']:.2f}s")
    print(f"  Std Dev: {timing_stats['std']:.2f}s")
    print(f"  Min: {timing_stats['min']:.2f}s")
    print(f"  Max: {timing_stats['max']:.2f}s")
    print(f"  95th percentile: {timing_stats['percentiles']['95']:.2f}s")


def plot_session_length_histogram(data: Dict, output_dir: Path):
    """Plot histogram of session lengths."""
    print("\nPlotting session length histogram...")
    
    session_stats = data['fsession_length']['statistics']
    sample_values = data['fsession_length']['sample_values']
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    ax.hist(sample_values, bins=50, edgecolor='black', alpha=0.7, color='seagreen')
    ax.set_xlabel('Session Length (number of events)')
    ax.set_ylabel('Frequency')
    ax.set_title('Session Length Distribution')
    ax.axvline(session_stats['median'], color='red', linestyle='--', 
               label=f"Median: {session_stats['median']:.1f}")
    ax.axvline(session_stats['mean'], color='orange', linestyle='--', 
               label=f"Mean: {session_stats['mean']:.1f}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_path = output_dir / "session_length_histogram.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_path}")
    plt.close()
    
    # Print statistics
    print("\nSession Length Statistics:")
    print(f"  Count: {session_stats['count']:,}")
    print(f"  Mean: {session_stats['mean']:.1f} events")
    print(f"  Median: {session_stats['median']:.1f} events")
    print(f"  Max: {session_stats['max']:.0f} events")


def plot_transition_matrix(data: Dict, output_dir: Path):
    """Plot artifact class transition matrix as heatmap."""
    print("\nPlotting transition matrix...")
    
    transition_matrix = data['faccess_transition_matrix']['matrix']
    
    # Get artifact classes from routing namespace
    artifact_classes = sorted(set([
        data['metadata']['routing_namespace'][0].replace('Event', '').replace('Issues', 'Issue')
        for _ in range(len(transition_matrix))
    ]))
    
    # Create a more readable version
    labels = [
        'Issue', 'PullRequest', 'Commit', 
        'IssueComment', 'PRComment', 'CommitComment'
    ][:len(transition_matrix)]
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Create heatmap
    im = ax.imshow(transition_matrix, cmap='YlOrRd', aspect='auto')
    
    # Set ticks and labels
    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.set_yticklabels(labels)
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Transition Probability', rotation=270, labelpad=20)
    
    # Add text annotations
    for i in range(len(labels)):
        for j in range(len(labels)):
            text = ax.text(j, i, f'{transition_matrix[i][j]:.3f}',
                          ha="center", va="center", color="black", fontsize=8)
    
    ax.set_xlabel('To Artifact Class')
    ax.set_ylabel('From Artifact Class')
    ax.set_title('Artifact Class Access Transition Matrix')
    
    plt.tight_layout()
    
    output_path = output_dir / "transition_matrix.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_path}")
    plt.close()


def plot_event_type_frequency(data: Dict, output_dir: Path):
    """Plot event type frequency distribution."""
    print("\nPlotting event type frequency...")
    
    frequencies = data['f_event_type_frequency']['frequencies']
    
    # Sort by frequency
    sorted_items = sorted(frequencies.items(), key=lambda x: x[1], reverse=True)
    event_types = [item[0].replace('Event', '') for item in sorted_items]
    counts = [item[1] for item in sorted_items]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    bars = ax.bar(event_types, counts, color='coral', edgecolor='black', alpha=0.7)
    ax.set_xlabel('Event Type')
    ax.set_ylabel('Frequency')
    ax.set_title('Event Type Distribution')
    ax.tick_params(axis='x', rotation=45)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height):,}',
                ha='center', va='bottom', fontsize=8)
    
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    
    output_path = output_dir / "event_type_frequency.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_path}")
    plt.close()


def plot_artifact_revisit(data: Dict, output_dir: Path):
    """Plot artifact revisit patterns."""
    print("\nPlotting artifact revisit patterns...")
    
    revisit_data = data['f_artifact_revisit']
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    # Revisit rate
    revisit_rate_values = revisit_data['revisit_rate']['sample_values']
    axes[0].hist(revisit_rate_values, bins=30, color='purple', 
                 edgecolor='black', alpha=0.7)
    axes[0].set_xlabel('Revisit Rate')
    axes[0].set_ylabel('Frequency')
    axes[0].set_title('Artifact Revisit Rate Distribution')
    axes[0].grid(True, alpha=0.3)
    
    # Unique artifacts
    unique_values = revisit_data['unique_artifacts']['sample_values']
    axes[1].hist(unique_values, bins=30, color='teal', 
                 edgecolor='black', alpha=0.7)
    axes[1].set_xlabel('Number of Unique Artifacts')
    axes[1].set_ylabel('Frequency')
    axes[1].set_title('Unique Artifacts per User')
    axes[1].grid(True, alpha=0.3)
    
    # Max revisits
    max_revisit_values = revisit_data['max_revisits']['sample_values']
    axes[2].hist(max_revisit_values, bins=30, color='darkgoldenrod', 
                 edgecolor='black', alpha=0.7)
    axes[2].set_xlabel('Max Revisits to Single Artifact')
    axes[2].set_ylabel('Frequency')
    axes[2].set_title('Maximum Revisit Count')
    axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_path = output_dir / "artifact_revisit.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_path}")
    plt.close()


def main():
    """Main plotting workflow."""
    print()
    print("="*70)
    print("BEHAVIORAL PRIORS VISUALIZATION")
    print("="*70)
    print()
    
    try:
        # Load data
        data = load_behavioral_priors(OUTPUT_JSON_PATH)
        
        # Create output directory
        output_dir = Path(OUTPUT_FIGURES_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nSaving figures to: {output_dir}/")
        
        # Generate all plots
        plot_timing_histogram(data, output_dir)
        plot_session_length_histogram(data, output_dir)
        plot_transition_matrix(data, output_dir)
        plot_event_type_frequency(data, output_dir)
        plot_artifact_revisit(data, output_dir)
        
        print()
        print("="*70)
        print(f"✓ All visualizations saved to {output_dir}/")
        print("="*70)
        print()
        
    except FileNotFoundError:
        print(f"\n✗ Error: {OUTPUT_JSON_PATH} not found!")
        print("Run extract_behavioral_priors.py first to generate the data.")
        print()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
