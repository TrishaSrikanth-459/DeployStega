"""
COMPLETE GMM PIPELINE
Downloads GitHub data from Hugging Face, trains GMM, generates D₁, validates

Data Source: https://huggingface.co/datasets/shivank21/gh_archive_june_week1

Tasks:
✓ Train GMM on Month-1 priors (D_train)
✓ Sample synthetic user timelines (D₁)
✓ Validate against held-out benign logs (D_test)

Artifacts:
✓ Synthetic behavioral logs (D1_synthetic_traces.json)
✓ Behavioral indistinguishability validation plots
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict
from collections import defaultdict, Counter
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from scipy.stats import ks_2samp, wasserstein_distance
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import sys
import gc
warnings.filterwarnings('ignore')

print("\n" + "="*70)
print("COMPLETE GMM PIPELINE - HUGGING FACE → D₁")
print("="*70)
print("Source: shivank21/gh_archive_june_week1")
print("="*70 + "\n")

#INSTALL AND IMPORT DATASETS

print("STEP 1: Setting up Hugging Face datasets...")
print("-"*70)

try:
    from datasets import load_dataset
    print("✓ datasets library already installed")
except ImportError:
    print("Installing datasets library...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "datasets", "--break-system-packages"])
    from datasets import load_dataset
    print("✓ datasets library installed")

#DOWNLOAD AND EXTRACT GITHUB EVENTS

print("\n" + "="*70)
print("STEP 2: DOWNLOADING GITHUB EVENTS FROM HUGGING FACE")
print("="*70)

DATASET_NAME = "shivank21/gh_archive_june_week1"
ROUTING_NAMESPACE = [
    "CreateEvent", "PullRequestEvent", "IssuesEvent",
    "PullRequestReviewEvent", "CommitCommentEvent",
    "IssueCommentEvent", "PushEvent", "PullRequestReviewCommentEvent"
]

MIN_EVENTS_PER_USER = 5
MAX_EVENTS_PER_USER = 1000
MAX_BATCHES = 100  

print(f"\nDataset: {DATASET_NAME}")
print(f"Event types: {len(ROUTING_NAMESPACE)}")
print(f"Min events per user: {MIN_EVENTS_PER_USER}")
print(f"Max batches to process: {MAX_BATCHES}")

print("\nLoading dataset (streaming mode)...")
try:
    dataset = load_dataset(DATASET_NAME, split="train", streaming=True)
    print("✓ Dataset loaded successfully\n")
except Exception as e:
    print(f"✗ Error loading dataset: {e}")
    raise

# Extract events
print("Extracting GitHub events...")
user_events = defaultdict(list)
total_events = 0
namespace_events = 0
batch_num = 0

for batch in dataset.iter(batch_size=10000):
    batch_num += 1
    
    if batch_num > MAX_BATCHES:
        print(f"\nReached max batches limit ({MAX_BATCHES})")
        break
    
    for i in range(len(batch['id'])):
        try:
            event_type = batch['type'][i]
            total_events += 1
            
            if event_type not in ROUTING_NAMESPACE:
                continue
            
            actor = batch['actor'][i]
            if not actor or 'id' not in actor:
                continue
            user_id = str(actor['id'])
            
            if len(user_events[user_id]) >= MAX_EVENTS_PER_USER:
                continue
            
            repo = batch['repo'][i]
            if not repo or 'id' not in repo:
                continue
            repo_id = str(repo['id'])
            
            timestamp_str = batch['created_at'][i]
            if not timestamp_str:
                continue
            
            timestamp = datetime.fromisoformat(
                str(timestamp_str).replace("Z", "+00:00")
            ).timestamp()
            
            event = {
                'timestamp': timestamp,
                'event_type': event_type,
                'artifact_id': repo_id,
            }
            
            user_events[user_id].append(event)
            namespace_events += 1
            
        except (KeyError, TypeError, ValueError):
            continue
    
    if batch_num % 10 == 0:
        pct = (namespace_events / max(total_events, 1)) * 100
        print(f"  Batch {batch_num}: {total_events:,} total ({namespace_events:,} / {pct:.1f}% in namespace), {len(user_events):,} users")
    
    gc.collect()

print(f"\n✓ Event extraction complete!")
print(f"  Total events: {total_events:,}")
print(f"  Namespace events: {namespace_events:,}")
print(f"  Users: {len(user_events):,}")

# Filter users with minimum events
filtered_users = {uid: events for uid, events in user_events.items() 
                  if len(events) >= MIN_EVENTS_PER_USER}

print(f"\n✓ Filtered to {len(filtered_users):,} users with ≥{MIN_EVENTS_PER_USER} events")

#EXTRACT BEHAVIORAL FEATURES (D)

print("\n" + "="*70)
print("STEP 3: EXTRACTING BEHAVIORAL FEATURES → D")
print("="*70)

def extract_sessions(events, gap_minutes=60):
    """Group events into sessions based on time gaps"""
    if not events:
        return []
    
    sorted_events = sorted(events, key=lambda e: e['timestamp'])
    sessions = []
    current_session = [sorted_events[0]]
    
    for event in sorted_events[1:]:
        time_gap = (event['timestamp'] - current_session[-1]['timestamp']) / 60
        
        if time_gap <= gap_minutes:
            current_session.append(event)
        else:
            sessions.append(current_session)
            current_session = [event]
    
    if current_session:
        sessions.append(current_session)
    
    return sessions

def session_to_features(session):
    """Convert session to behavioral features"""
    if not session:
        return None
    
    timestamps = [e['timestamp'] for e in session]
    start_time = min(timestamps)
    end_time = max(timestamps)
    duration_min = (end_time - start_time) / 60 if len(session) > 1 else 1.0
    
    events_count = len(session)
    repos_visited = len(set(e['artifact_id'] for e in session))
    
    # Event diversity (entropy)
    event_types = [e['event_type'] for e in session]
    type_counts = Counter(event_types)
    total = sum(type_counts.values())
    probs = [c / total for c in type_counts.values()]
    event_diversity = -sum(p * np.log2(p) for p in probs if p > 0)
    
    # Activity intensity
    activity_intensity = events_count / max(duration_min, 1)
    
    # Inter-event timing
    if len(session) > 1:
        time_diffs = [(timestamps[i+1] - timestamps[i]) / 60 for i in range(len(timestamps) - 1)]
        avg_inter_event_time = np.mean(time_diffs)
    else:
        avg_inter_event_time = 0
    
    # Primary event type
    primary_event_type = type_counts.most_common(1)[0][0]
    
    # Temporal features
    dt = datetime.fromtimestamp(start_time)
    
    return {
        'timestamp': dt.isoformat(),
        'session_duration_min': float(duration_min),
        'events_count': int(events_count),
        'repos_visited': int(repos_visited),
        'event_diversity': float(event_diversity),
        'activity_intensity': float(activity_intensity),
        'avg_inter_event_time': float(avg_inter_event_time),
        'primary_event_type': primary_event_type,
        'hour_of_day': int(dt.hour),
        'day_of_week': int(dt.weekday())
    }

# Extract features for all users
print("Extracting behavioral features from sessions...")
all_sessions = []

for i, (user_id, events) in enumerate(filtered_users.items(), 1):
    sessions = extract_sessions(events)
    
    for session in sessions:
        features = session_to_features(session)
        if features:
            features['user_id'] = user_id
            all_sessions.append(features)
    
    if i % 500 == 0:
        print(f"  Processed {i:,} users ({len(all_sessions):,} sessions)...")

D = pd.DataFrame(all_sessions)

# Add session_frequency_day
date_counts = Counter(datetime.fromisoformat(s['timestamp']).date() for s in all_sessions)
for session in all_sessions:
    session_date = datetime.fromisoformat(session['timestamp']).date()
    session['session_frequency_day'] = date_counts[session_date]

D = pd.DataFrame(all_sessions)

print(f"\n✓ Extracted D: {len(D):,} behavioral sessions")
print(f"  Unique users: {D['user_id'].nunique():,}")
print(f"  Avg sessions/user: {len(D) / D['user_id'].nunique():.1f}")

print("\nBehavioral Feature Statistics:")
print(f"  Session duration: {D['session_duration_min'].mean():.1f} ± {D['session_duration_min'].std():.1f} min")
print(f"  Events/session: {D['events_count'].mean():.1f} ± {D['events_count'].std():.1f}")
print(f"  Repos/session: {D['repos_visited'].mean():.1f} ± {D['repos_visited'].std():.1f}")

#TRAIN/TEST SPLIT

print("\n" + "="*70)
print("STEP 4: SPLITTING D INTO D_train (70%) AND D_test (30%)")
print("="*70)

D_train, D_test = train_test_split(D, test_size=0.3, random_state=42)

print(f"D_train: {len(D_train):,} sessions (70%)")
print(f"D_test:  {len(D_test):,} sessions (30%)")

#TRAIN GMM MODEL

print("\n" + "="*70)
print("STEP 5: TRAINING GMM ON D_train")
print("="*70)

numerical_features = [
    'session_duration_min',
    'events_count',
    'repos_visited',
    'event_diversity',
    'activity_intensity',
    'avg_inter_event_time'
]

# Extract and normalize
X_train = D_train[numerical_features].values
scaler = StandardScaler()
X_train_normalized = scaler.fit_transform(X_train)

# Train GMM
n_components = 8
print(f"Training GMM with {n_components} components.")

gmm = GaussianMixture(
    n_components=n_components,
    covariance_type='full',
    random_state=42,
    max_iter=200,
    verbose=0
)

gmm.fit(X_train_normalized)

log_likelihood = gmm.score(X_train_normalized)
bic = gmm.bic(X_train_normalized)
aic = gmm.aic(X_train_normalized)

print(f"\n✓ GMM Training Complete!")
print(f"  Components: {n_components}")
print(f"  Log-likelihood: {log_likelihood:.4f}")
print(f"  BIC: {bic:.2f}")
print(f"  AIC: {aic:.2f}")

print(f"\nLearned User Archetypes (GMM Components):")
for i in range(min(5, n_components)): 
    weight = gmm.weights_[i]
    mean = scaler.inverse_transform([gmm.means_[i]])[0]
    print(f"\n  Component {i+1} ({weight*100:.1f}% of users):")
    print(f"    Avg session duration: {mean[0]:.1f} min")
    print(f"    Avg events: {mean[1]:.1f}")
    print(f"    Avg repos: {mean[2]:.1f}")
    print(f"    Avg diversity: {mean[3]:.2f}")

# Learn temporal distributions
event_type_dist = D_train['primary_event_type'].value_counts(normalize=True).to_dict()
hour_dist = D_train['hour_of_day'].value_counts(normalize=True).to_dict()
day_dist = D_train['day_of_week'].value_counts(normalize=True).to_dict()

# GENERATE D₁ (SYNTHETIC TRACES)

print("\n" + "="*70)
print("STEP 6: GENERATING D₁ (SYNTHETIC BEHAVIORAL TRACES)")
print("="*70)

n_synthetic_users = 50
sessions_per_user = 30
total_synthetic_sessions = n_synthetic_users * sessions_per_user

print(f"Generating {n_synthetic_users} synthetic users...")
print(f"Sessions per user: {sessions_per_user}")
print(f"Total synthetic sessions: {total_synthetic_sessions}")

# Generate synthetic timelines
D1_timelines = []

for user_idx in range(n_synthetic_users):
    user_id = f'synth_user_{user_idx:04d}'
    timeline = []
    
    start_date = datetime(2024, 6, 1)
    current_date = start_date
    
    for session_idx in range(sessions_per_user):
        # Sample from GMM
        X_synth_norm = gmm.sample(1)[0][0]
        X_synth = scaler.inverse_transform([X_synth_norm])[0]
        X_synth = np.maximum(X_synth, 0)
        
        # Sample temporal features
        hour = np.random.choice(list(hour_dist.keys()), p=list(hour_dist.values()))
        day = np.random.choice(list(day_dist.keys()), p=list(day_dist.values()))
        event_type = np.random.choice(list(event_type_dist.keys()), p=list(event_type_dist.values()))
        
        # Update timestamp
        if session_idx > 0:
            hours_gap = np.random.gamma(2, 3)
            current_date += timedelta(hours=hours_gap)
        
        current_date = current_date.replace(hour=hour, minute=np.random.randint(0, 60))
        
        session = {
            'user_id': user_id,
            'timestamp': current_date.isoformat(),
            'session_id': f'synth_{user_id}_{session_idx}',
            'session_duration_min': float(X_synth[0]),
            'events_count': int(max(1, round(X_synth[1]))),
            'repos_visited': int(max(1, round(X_synth[2]))),
            'event_diversity': float(max(0, X_synth[3])),
            'activity_intensity': float(max(0, X_synth[4])),
            'avg_inter_event_time': float(max(0, X_synth[5])),
            'primary_event_type': event_type,
            'hour_of_day': int(hour),
            'day_of_week': int(day),
            'session_frequency_day': np.random.randint(1, 5),
            'is_synthetic': True
        }
        
        timeline.append(session)
    
    D1_timelines.append(timeline)
    
    if (user_idx + 1) % 10 == 0:
        print(f"  Generated {user_idx+1}/{n_synthetic_users} users...")

# Flatten for validation
D1 = pd.DataFrame([s for timeline in D1_timelines for s in timeline])

print(f"\n✓ Generated D₁: {len(D1):,} synthetic sessions")

#VALIDATE D_test vs D₁

print("\n" + "="*70)
print("STEP 7: VALIDATING D_test vs D₁ FOR INDISTINGUISHABILITY")
print("="*70)

validation_results = {
    'ks_tests': {},
    'wasserstein_distances': {},
    'statistical_summary': {}
}

print("\nRunning Statistical Tests:")
print("-"*70)
print(f"{'Feature':<30} {'p-value':<12} {'W-dist':<12} {'Status':<10}")
print("-"*70)

for feature in numerical_features:
    real_vals = D_test[feature].values
    synth_vals = D1[feature].values
    
    # KS test
    ks_stat, p_value = ks_2samp(real_vals, synth_vals)
    
    # Wasserstein
    w_dist = wasserstein_distance(real_vals, synth_vals)
    
    validation_results['ks_tests'][feature] = {
        'p_value': float(p_value),
        'indistinguishable': bool(p_value > 0.05)
    }
    validation_results['wasserstein_distances'][feature] = float(w_dist)
    validation_results['statistical_summary'][feature] = {
        'D_mean': float(np.mean(real_vals)),
        'D1_mean': float(np.mean(synth_vals)),
        'D_std': float(np.std(real_vals)),
        'D1_std': float(np.std(synth_vals))
    }
    
    status = "✓ PASS" if p_value > 0.05 else "✗ FAIL"
    print(f"{feature:<30} {p_value:<12.4f} {w_dist:<12.4f} {status:<10}")

indist_count = sum(1 for v in validation_results['ks_tests'].values() if v['indistinguishable'])
indist_rate = indist_count / len(numerical_features)
validation_results['overall_indistinguishability_rate'] = float(indist_rate)

print("-"*70)
print(f"\n{'='*70}")
print(f"INDISTINGUISHABILITY RATE: {indist_rate:.1%}")
print(f"{'='*70}")
print(f"Features passing KS test (p > 0.05): {indist_count}/{len(numerical_features)}")

#CREATE VALIDATION PLOTS

print("\n" + "="*70)
print("STEP 8: CREATING VALIDATION PLOTS")
print("="*70)

fig, axes = plt.subplots(2, 3, figsize=(15, 10))
axes = axes.flatten()

for idx, feature in enumerate(numerical_features):
    ax = axes[idx]
    
    ax.hist(D_test[feature], bins=30, alpha=0.5, label='D (Real)', 
            density=True, color='blue', edgecolor='black', linewidth=0.5)
    ax.hist(D1[feature], bins=30, alpha=0.5, label='D₁ (Synthetic)', 
            density=True, color='orange', edgecolor='black', linewidth=0.5)
    
    p_val = validation_results['ks_tests'][feature]['p_value']
    status = "✓" if p_val > 0.05 else "✗"
    
    ax.set_title(f"{feature.replace('_', ' ').title()}\np-value: {p_val:.4f} {status}", 
                 fontsize=10, fontweight='bold')
    ax.set_xlabel(feature.replace('_', ' ').title(), fontsize=9)
    ax.set_ylabel('Density', fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

plt.suptitle(f'D vs D₁ Behavioral Indistinguishability\nOverall Score: {indist_rate:.1%}', 
             fontsize=14, fontweight='bold', y=0.995)
plt.tight_layout()

plot_path = '/mnt/user-data/outputs/D_vs_D1_validation.png'
plt.savefig(plot_path, dpi=300, bbox_inches='tight')
print(f"✓ Saved validation plot: {plot_path}")
plt.close()

# SAVE ALL OUTPUTS

print("\n" + "="*70)
print("STEP 9: SAVING ALL OUTPUTS")
print("="*70)

output_dir = '/mnt/user-data/outputs'

# Save D
D.to_json(f'{output_dir}/D_real_traces.json', orient='records', indent=2)
print("✓ Saved D_real_traces.json")

# Save splits
D_train.to_json(f'{output_dir}/D_train.json', orient='records', indent=2)
print("✓ Saved D_train.json")

D_test.to_json(f'{output_dir}/D_test.json', orient='records', indent=2)
print("✓ Saved D_test.json")

# Save D1 (timelines format)
with open(f'{output_dir}/D1_synthetic_traces.json', 'w') as f:
    json.dump(D1_timelines, f, indent=2)
print("✓ Saved D1_synthetic_traces.json ⭐")

# Save validation
with open(f'{output_dir}/D_vs_D1_validation.json', 'w') as f:
    json.dump(validation_results, f, indent=2)
print("✓ Saved D_vs_D1_validation.json")

# FINAL SUMMARY
print("\n" + "="*70)
print("🎉 PIPELINE COMPLETE - ALL DELIVERABLES READY!")
print("="*70)

print("\n📊 SUMMARY:")
print(f"  D (Real):              {len(D):,} sessions")
print(f"  D_train (70%):         {len(D_train):,} sessions")
print(f"  D_test (30%):          {len(D_test):,} sessions")
print(f"  D₁ (Synthetic):        {len(D1):,} sessions")
print(f"  Indistinguishability:  {indist_rate:.1%}")

print("\n📁 OUTPUT FILES:")
print("  D_real_traces.json           - All real behavioral traces")
print("  D_train.json                 - Training set (70%)")
print("  D_test.json                  - Test set (30%)")
print("  D1_synthetic_traces.json     - Synthetic traces ⭐")
print("  D_vs_D1_validation.json      - Statistical validation")
print("  D_vs_D1_validation.png       - Validation plots")

print("\n🎯 TASKS COMPLETED:")
print("  ✅ Train GMM on Month-1 priors (D_train)")
print("  ✅ Sample synthetic user timelines (D₁)")
print("  ✅ Validate against held-out benign logs (D_test)")

print("\n📦 ARTIFACTS DELIVERED:")
print("  ✅ Synthetic behavioral logs (D1_synthetic_traces.json)")
print("  ✅ Behavioral indistinguishability validation plots")

print("\n" + "="*70)
print("✨ ALL REQUIREMENTS MET - PROJECT COMPLETE! ✨")
print("="*70 + "\n")
