import pandas as pd
import numpy as np
import itertools
import os

def create_co_citation_matrix(references_df, target_authors, output_path):
    """
    Creates a co-citation matrix from a dataframe of references and a list of target authors.
    """
    print(f"Processing {len(references_df)} references for {output_path}...")
    
    # 1. Filter references to include only those in the target author list
    if 'LOD이름' not in references_df.columns:
        print("Error: 'LOD이름' column not found in reference data.")
        return

    # Clean author names in reference data for matching
    references_df = references_df.copy()
    references_df['LOD이름_clean'] = references_df['LOD이름'].astype(str).str.strip()
    
    # Filter rows where the cited author is in our target list
    relevant_refs = references_df[references_df['LOD이름_clean'].isin(target_authors)].copy()
    print(f"Filtered down to {len(relevant_refs)} relevant citations.")

    if len(relevant_refs) == 0:
        print("No matching citations found.")
        return

    # 2. Group by 'art-id' to find co-citations
    # Initialize adjacency matrix
    sorted_authors = sorted(target_authors)
    adj_matrix = pd.DataFrame(0, index=sorted_authors, columns=sorted_authors)

    # Group by paper ID
    grouped = relevant_refs.groupby('art-id')['LOD이름_clean'].apply(list)

    print("Calculating co-citation counts...")
    count = 0
    for art_id, authors in grouped.items():
        unique_authors = list(set(authors))
        
        if len(unique_authors) > 1:
            for a1, a2 in itertools.combinations(unique_authors, 2):
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

def main():
    base_dir = "/Users/cosi/Library/CloudStorage/GoogleDrive-vadoropupille@gmail.com/공유 드라이브/ProjJCA/[최종] 작업 데이터/[최종] 한국문학"
    pkl_path = '/Users/cosi/Library/CloudStorage/GoogleDrive-vadoropupille@gmail.com/공유 드라이브/ProjJCA/[최종] 작업 데이터/한국문학.pkl'
    
    references_file = os.path.join(base_dir, "한국문학_참고문헌_분석용.csv")
    top100_file = os.path.join(base_dir, "한국문학_외국인저자_top100.csv")
    
    output_period1 = os.path.join(base_dir, "period_cocitation_matrix_upto2015.csv")
    output_period2 = os.path.join(base_dir, "period_cocitation_matrix_from2016.csv")

    print("Loading data...")
    try:
        # Load Top 100 Authors
        top100_df = pd.read_csv(top100_file)
        target_authors = top100_df['대표저자'].dropna().astype(str).str.strip().unique()
        print(f"Found {len(target_authors)} target authors.")

        # Load References
        ref_df = pd.read_csv(references_file)
        print(f"Loaded {len(ref_df)} references.")

        # Load Metadata (PKL)
        try:
            meta_df = pd.read_pickle(pkl_path)
        except ImportError:
             import pickle
             with open(pkl_path, 'rb') as f:
                 meta_df = pickle.load(f)
        
        print(f"Loaded metadata with {len(meta_df)} papers.")
        
        # Verify columns
        if 'article-id' not in meta_df.columns:
            print("Error: 'article-id' column not found in PKL file.")
            print("Columns available:", meta_df.columns.tolist())
            return
        
        if 'pub-year' not in meta_df.columns:
             print("Error: 'pub-year' column not found in PKL file.")
             return

    except Exception as e:
        print(f"Error loading data: {e}")
        return

    # Merge Reference Data with Metadata
    print("Merging reference data with metadata...")
    
    # Ensure ID types match (string)
    ref_df['art-id'] = ref_df['art-id'].astype(str).str.strip()
    meta_df['article-id'] = meta_df['article-id'].astype(str).str.strip()
    
    # Rename pub-year in metadata to avoid collision with ref_df
    meta_df = meta_df.rename(columns={'pub-year': 'citing_pub_year'})

    # Merge
    merged_df = pd.merge(ref_df, meta_df[['article-id', 'citing_pub_year']], left_on='art-id', right_on='article-id', how='left')
    
    print(f"Merged data has {len(merged_df)} rows.")
    
    # Clean pub-year
    print("Cleaning citing_pub_year column...")
    merged_df['pub_year_clean'] = pd.to_numeric(merged_df['citing_pub_year'], errors='coerce')
    
    # Check for invalid years
    missing_year_count = merged_df['pub_year_clean'].isna().sum()
    print(f"Rows with invalid or missing year info: {missing_year_count}")
    
    # Drop rows with missing year for analysis
    valid_df = merged_df.dropna(subset=['pub_year_clean'])
    
    # Define groups
    # Period 1: <= 2015
    # Period 2: >= 2016
    period1_refs = valid_df[valid_df['pub_year_clean'] <= 2015]
    period2_refs = valid_df[valid_df['pub_year_clean'] >= 2016]

    print(f"Period 1 (<= 2015) references: {len(period1_refs)}")
    print(f"Period 2 (>= 2016) references: {len(period2_refs)}")

    # Analysis for Period 1
    print("\n--- Processing Period 1 (<= 2015) ---")
    create_co_citation_matrix(period1_refs, target_authors, output_period1)

    # Analysis for Period 2
    print("\n--- Processing Period 2 (>= 2016) ---")
    create_co_citation_matrix(period2_refs, target_authors, output_period2)
    
    print("\nAnalysis complete.")

if __name__ == "__main__":
    main()
