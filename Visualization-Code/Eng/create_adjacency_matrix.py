import pandas as pd
import numpy as np
import itertools
import os

def create_co_citation_matrix(top100_path, references_path, output_path):
    print("Loading data...")
    # Load the top 100 foreign authors file
    try:
        top100_df = pd.read_csv(top100_path)
        # Extract the list of target authors. Strip whitespace just in case.
        target_authors = top100_df['대표저자'].dropna().astype(str).str.strip().unique()
        print(f"Found {len(target_authors)} target authors.")
    except Exception as e:
        print(f"Error loading {top100_path}: {e}")
        return

    # Load the reference data
    try:
        # Loading a potentially large file
        ref_df = pd.read_csv(references_path)
        print(f"Loaded reference data with {len(ref_df)} rows.")
    except Exception as e:
        print(f"Error loading {references_path}: {e}")
        return

    # 1. Filter references to include only those in the target author list
    # Ensure 'LOD이름' column exists and clean it
    if 'LOD이름' not in ref_df.columns:
        print("Error: 'LOD이름' column not found in reference file.")
        return
    
    # Clean author names in reference data for matching
    ref_df['LOD이름_clean'] = ref_df['LOD이름'].astype(str).str.strip()
    
    # Filter rows where the cited author is in our target list
    relevant_refs = ref_df[ref_df['LOD이름_clean'].isin(target_authors)].copy()
    print(f"Filtered down to {len(relevant_refs)} relevant citations.")

    if len(relevant_refs) == 0:
        print("No matching citations found. Check if author names match exactly between files.")
        return

    # 2. Group by 'art-id' to find co-citations
    # We want papers ('art-id') that cite multiple *different* target authors
    
    # Initialize adjacency matrix
    # Rows and Columns are the target authors
    # Sort authors for consistent ordering
    sorted_authors = sorted(target_authors)
    adj_matrix = pd.DataFrame(0, index=sorted_authors, columns=sorted_authors)

    # Group by paper ID
    grouped = relevant_refs.groupby('art-id')['LOD이름_clean'].apply(list)
    # Group by paper ID and get unique authors for each paper
    # grouped = relevant_refs.groupby('art-id')['LOD이름_clean'].unique()

    print("Processing co-citations...")
    count = 0
    for art_id, authors in grouped.items():
        if len(authors) > 1:
            # Generate all pairs of authors in this paper
            # combinations('ABCD', 2) --> AB AC AD BC BD CD
            for a1, a2 in itertools.combinations(authors, 2):
                # Update matrix (symmetric)
                adj_matrix.loc[a1, a2] += 1
                adj_matrix.loc[a2, a1] += 1
            count += 1
    
    print(f"Processed {count} papers with co-citations.")

    # 3. Save the result
    try:
        adj_matrix.to_csv(output_path)
        print(f"Adjacency matrix saved to {output_path}")
    except Exception as e:
        print(f"Error saving output: {e}")

if __name__ == "__main__":
    base_dir = "/Users/cosi/Library/CloudStorage/GoogleDrive-vadoropupille@gmail.com/공유 드라이브/ProjJCA/[최종] 작업 데이터/[최종] 영문학"
    top100_file = os.path.join(base_dir, "영문학_외국인저자_top100.csv")
    ref_file = os.path.join(base_dir, "영문학_참고문헌_분석용.csv")
    output_file = os.path.join(base_dir, "co_citation_matrix.csv")

    create_co_citation_matrix(top100_file, ref_file, output_file)
