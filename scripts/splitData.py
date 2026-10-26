import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


def split_spam_dataset(
    csv_path='spam.csv',
    num_clients=5,
    test_ratio=0.15,
    val_ratio=0.15,
    random_seed=42,
    non_iid_strength=0.4,
):
  """Reads the spam dataset and splits it into:

  1. Final Test Set (held-out for evaluation)
  2. Coordinator Validation Set (for update validation & trust scoring)
  3. Non-IID Client Training Partitions
  """
  # 1. Load dataset
  # Adjust column names ('v1'/'v2' or 'label'/'text') depending on your CSV headers
  # The UCI SMS Spam Collection uses ISO-8859-1 characters.
  df = pd.read_csv(csv_path, encoding='latin-1')

  # Auto-detect label and text columns if named standard SMS spam format
  if 'v1' in df.columns and 'v2' in df.columns:
    df = df.rename(columns={'v1': 'label', 'v2': 'text'})

  # Standardize label values: 1 for spam, 0 for ham/legitimate
  if df['label'].dtype == object:
    df['label'] = (
        df['label'].astype(str).str.lower().map({'spam': 1, 'ham': 0})
    )

  # Keep only necessary columns
  df = df[['text', 'label']].dropna().reset_index(drop=True)

  # 2. Split out Final Test Set
  train_val_df, test_df = train_test_split(
      df, test_size=test_ratio, random_state=random_seed, stratify=df['label']
  )

  # 3. Split out Coordinator Validation Set
  adjusted_val_ratio = val_ratio / (1.0 - test_ratio)
  train_df, val_df = train_test_split(
      train_val_df,
      test_size=adjusted_val_ratio,
      random_state=random_seed,
      stratify=train_val_df['label'],
  )

  print(f'Total Dataset: {len(df)} records')
  print(f'|-- Final Test Set: {len(test_df)} records')
  print(f'|-- Coordinator Validation Set: {len(val_df)} records')
  print(f'`-- Training Pool: {len(train_df)} records\n')

  # 4. Partition Training Data Non-IID across Clients
  if num_clients < 1:
    raise ValueError('num_clients must be at least 1')
  if not 0 <= non_iid_strength <= 1:
    raise ValueError('non_iid_strength must be between 0 and 1')

  # Give each client a similar size while allowing a controlled label skew.
  client_indices = np.array_split(np.arange(len(train_df)), num_clients)
  client_sizes = np.array([len(indices) for indices in client_indices])
  label_counts = train_df['label'].value_counts()
  spam_total = int(label_counts.get(1, 0))
  ham_total = int(label_counts.get(0, 0))
  if spam_total < num_clients or ham_total < num_clients:
    raise ValueError('The training set must contain both labels for every client')

  global_spam_rate = spam_total / len(train_df)
  client_profile = np.linspace(-1, 1, num_clients)
  target_rates = global_spam_rate * (
      1 + non_iid_strength * client_profile
  )
  raw_spam_counts = client_sizes * target_rates
  spam_counts = np.floor(raw_spam_counts).astype(int)
  remainder = spam_total - int(spam_counts.sum())
  for index in np.argsort(-(raw_spam_counts - spam_counts))[:remainder]:
    spam_counts[index] += 1

  spam_rows = train_df[train_df['label'] == 1].sample(
      frac=1, random_state=random_seed
  )
  ham_rows = train_df[train_df['label'] == 0].sample(
      frac=1, random_state=random_seed + 1
  )
  spam_offset = 0
  ham_offset = 0

  client_files = []
  for idx, client_size in enumerate(client_sizes):
    # Shuffle local partition so order inside the client file is randomized
    spam_count = int(spam_counts[idx])
    ham_count = int(client_size - spam_count)
    spam_chunk = spam_rows.iloc[spam_offset : spam_offset + spam_count]
    ham_chunk = ham_rows.iloc[ham_offset : ham_offset + ham_count]
    spam_offset += spam_count
    ham_offset += ham_count
    chunk = pd.concat([spam_chunk, ham_chunk])
    client_df = chunk.sample(frac=1, random_state=random_seed).reset_index(
        drop=True
    )

    spam_cnt = (client_df['label'] == 1).sum()
    ham_cnt = (client_df['label'] == 0).sum()
    filename = f'client_{idx + 1}_train.csv'

    client_df.to_csv(filename, index=False)
    client_files.append(filename)

    print(
        f'Client {idx + 1} Dataset ({filename}): {len(client_df)} samples |'
        f' Spam: {spam_cnt}, Ham: {ham_cnt}'
    )

  # 5. Save validation and test sets
  test_df.to_csv('final_test_set.csv', index=False)
  val_df.to_csv('coordinator_val_set.csv', index=False)

  print('\nFiles generated successfully:')
  print('  - final_test_set.csv')
  print('  - coordinator_val_set.csv')
  for f in client_files:
    print(f'  - {f}')


if __name__ == '__main__':
  split_spam_dataset('spam.csv')