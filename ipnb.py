# %% [markdown]
# Aging Provision Policy – Additional Provision Calculation 
# 
# Policy Overview
# To ensure prudent financial coverage, additional provisions are calculated for inventory in special categories, using the following rules:
# 
# 1. Damaged Inventory
# Provision Rate:
# 100% of the net total cost of damaged stock.
# 2. Leftover Inventory
# For Closed Brands:
# 50% of the net total cost of leftover stock from brands that are closed.
# For Running Brands:
# 15% of the net total cost of leftover stock from brands that are still operating.
# 3. Closed Brands (Other Locations)
# Provision Rate:
# 50% of the net total cost of stock from closed brands (excluding leftover and damaged locations).
# 4. Exclusions
# No additional provision is made for inventory under consignment, guaranteed margin, or “Buying Pull - Mango” models.
# Summary:
# These additional provisions are applied on top of the standard aging policy to ensure adequate financial coverage for higher-risk inventory categories.

# %% [markdown]
# 1. update the closed brands status in the mapping file
# 2. check the totals of the net cost throughout the steps to ensure the completness
# 3. update the combinations in the combination file
# 4. check missing standard brands in the mapping file and soh
# 5. check std season and buckets in the checks section of the code
# 6. update the parameters below
# 7. check for garbage std season in the code
# 8. ensure no duplicates in the combination[std brand name and location name] and mapping file [original brand name]
#  

# %%
import pandas as pd
import numpy as np
import os
pd.options.display.float_format = '{:,.2f}'.format

# %% [markdown]
# parameters

# %%

SOH_File = 'SOH-mar.xlsx'
first_first_bucket_number_seasons = 5
damage_percentage = 1
leftover_running_percentage = .15
leftover_closed_percentage = .5
closed_percentage = .5

brand_specific_provision = {}
'''    'FLYING TIGER': 2
}'''

# %%
import re

def season_sort_key(season):
    if not isinstance(season, str) or len(season) < 4:
        return (0, 0)  # Push unknowns to bottom

    season_type = season[:2]  # 'AW' or 'SS'
    year = int(season[-2:])

    # AW should come *before* SS, so give it a higher priority
    season_rank = 1 if season_type == "AW" else 0

    return (year, season_rank)

def standardize_season(raw_season):
    if not isinstance(raw_season, str) or raw_season.strip() == "":
        return "Unknown"

    season = raw_season.strip().upper()

    # --- Priority: continuity/old ---
    if "CONTINUITY" in season or "BASICS" in season:
        return "Continuity"

    elif "OLD" in season:
        return "Old-"

    # --- 4-digit year + seasonal tag ---
    year_match = re.search(r"(20\d{2})", season)
    if year_match:
        year = year_match.group(1)[2:]  # Take last 2 digits, e.g., '2023' → '23'

        if any(tag in season for tag in ["SPRING", "SUMMER", "SS"]):
            return f"SS{year}"
        elif any(tag in season for tag in ["AUTUMN", "WINTER", "AW"]):
            return f"AW{year}"

    # --- 2-digit season pattern like AW23, SS22 ---
    match = re.search(r"(SS|AW)(\d{2})", season)
    if match:
        return f"{match.group(1)}{match.group(2)}"

    # --- WA fallback to AW ---
    if "WA" in season:
        match = re.search(r"WA(\d{2})", season)
        if match:
            return f"AW{match.group(1)}"

    # --- Last resort: any 2-digit year with best guess ---
    match = re.search(r"(\d{2})", season)
    if match:
        return f"SS{match.group(1)}"
    
    return "Unknown"  # default if nothing matches


# %% [markdown]
# aging provision as per policy

# %%
soh = pd.read_excel(fr"SOH/{SOH_File}", sheet_name='Sheet1')
soh = soh[(soh['GROUP_NAME'] != 'Aleph' )& (soh['AR Comments'] == 'Consider')]
existing_balances = pd.read_excel(r'Existing Balances/current_balance.xlsx', sheet_name='Sheet1')
mapping = pd.read_excel(r'Mapping & Combinations/mapping.xlsx', sheet_name='Sheet1')

soh['NETTOTAL_COST'].fillna(0, inplace=True)
soh['NETTOTAL_COST'] = pd.to_numeric(soh['NETTOTAL_COST'], errors='coerce')

original_season = 'SEASON_DESC' if 'SEASON_DESC' in soh.columns else 'SEASON DESC'
soh['NETTOTAL_COST'].sum()


# %%
combinations = pd.read_excel(r'Mapping & Combinations/combinations.xlsx', sheet_name='Sheet1')
combinations = combinations.groupby(['LOCATION','Std Brand']).first().reset_index()

# %%
soh['GROUP_NAME'] = soh['GROUP_NAME'].str.upper()
mapping['GROUP_NAME'] = mapping['GROUP_NAME'].str.upper()
soh = soh.merge(mapping, on='GROUP_NAME', how='left')
#soh['Std Brand'] = np.where(soh['Std Brand'].isna(), soh['GROUP_NAME'], soh['Std Brand'])
soh = soh[(soh['Closed_status'] != 'Exit' )]
soh['NETTOTAL_COST'].sum()

# %%
'''valid_brands = soh.groupby('Std Brand')['NETTOTAL_COST'].sum()
valid_brands = valid_brands[valid_brands != 0].index

# Step 2: filter original DataFrame
soh = soh[soh['Std Brand'].isin(valid_brands)]
soh['NETTOTAL_COST'].sum()'''

# %%
soh['std_season'] = soh[original_season].apply(standardize_season)

# %%
excluded = {'Unknown', 'Continuity', 'Old-','AW97'}
unique_season = [f for f in soh['std_season'].dropna().unique() if f not in excluded]

# %%
sorted_std_season_in_soh = sorted(unique_season, key=season_sort_key, reverse=True)

# %%
bucket1 = sorted_std_season_in_soh[:first_first_bucket_number_seasons]
bucket2 = sorted_std_season_in_soh[first_first_bucket_number_seasons:first_first_bucket_number_seasons + 3]
bucket3 = sorted_std_season_in_soh[first_first_bucket_number_seasons+3:first_first_bucket_number_seasons + 6] 
bucket4 = sorted_std_season_in_soh[first_first_bucket_number_seasons + 6:]

# %%
bucket1

# %%
bucket1 =   bucket1 + ['Unknown','Continuity'] 
bucket4 = bucket4 + [  'Old-','AW97'] 

# %%

conditions = [
    soh['std_season'].isin(bucket1),
    soh['std_season'].isin(bucket2),
    soh['std_season'].isin(bucket3)
]

choices = ['bucket1', 'bucket2', 'bucket3']

soh['season_bucket'] = np.select(conditions, choices, default='bucket4')

# %%
soh['Continuity_factor'] = 0.40
soh['provision_%_policy'] = soh['season_bucket'].map({
    'bucket1': 0,
    'bucket2': 0.15,
    'bucket3': 0.50,
    'bucket4': 0.75  # Assuming bucket4 is the default for other buckets

})  # Or any default value for other buckets like 'bucket3', 'bucket4'

# %%

soh.loc[
    soh['Model'].isin([
        'Consignment',
        'Guaranteed Margin',
        'Buying Pull - Mango'
    ]),
    ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor']
] = 0

soh['provision_amount_policy'] = soh['NETTOTAL_COST'] * soh['provision_%_policy'] * soh['Continuity_factor']

# %% [markdown]
# Damage locations
# 

# %%
soh['location_catergory'] = "Store, Online & WH"

soh.loc[
    soh['LOCATION_NAME'].astype(str).str.lower().str.contains('leftover', na=False),
    "location_catergory"
] = "Leftover"
soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('damage', na=False),"location_catergory"] = "Damage"
soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('sulay', na=False),"location_catergory"] = "Leftover"

# %%
condition = soh['location_catergory'] == "Damage"  


soh.loc[condition, 'additional_provision'] = (soh["NETTOTAL_COST"] * damage_percentage) - soh['provision_amount_policy']



# %% [markdown]
# Leftover

# %%

#Leftover of the closed brands
condition =(
    (soh['Closed_status'] == "Closed") & 
    ( soh['location_catergory'] == "Leftover" ) 
    ) 

soh.loc[condition, 'additional_provision'] = (soh["NETTOTAL_COST"] * leftover_closed_percentage) - soh['provision_amount_policy']

condition =(
    (soh['Closed_status'] != "Closed") & 
    ( soh['location_catergory'] == "Leftover" ) 
    ) 

soh.loc[condition, 'additional_provision'] = (soh["NETTOTAL_COST"] * leftover_running_percentage) - soh['provision_amount_policy']


# %% [markdown]
# Closed brands

# %%
condition = (
    (soh['Closed_status'] == "Closed") & 
    (~soh['location_catergory'].isin(["Leftover","Damage"] )) 
    )
soh.loc[condition, 'additional_provision'] =    (soh["NETTOTAL_COST"] * closed_percentage) - soh['provision_amount_policy']

# %% [markdown]
# Brand specific provisions

# %%
if brand_specific_provision:
    soh['additional_provision'] = np.where(
        soh['Std Brand'].isin(brand_specific_provision.keys()),
        soh['NETTOTAL_COST'] * soh['Std Brand'].map(brand_specific_provision) - soh['provision_amount_policy'],
        soh['additional_provision']
    )

# %% [markdown]
# removing the consginement and gurantee margin provision

# %%
soh.loc[
    soh['Model'].isin([
        'Consignment',
        'Guaranteed Margin',
        'Buying Pull - Mango'
    ]),
    ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor','additional_provision']
] = 0

soh['provision_amount_policy'] = soh['provision_amount_policy'].fillna(0)
soh['additional_provision'] = soh['additional_provision'].fillna(0)


soh['Total Provision'] = soh['provision_amount_policy'] + soh['additional_provision']

# %%
soh.to_csv(r"Output/aging_provision.csv")

# %% [markdown]
# Summary

# %%
summary = soh.groupby(by='Std Brand')[["NETTOTAL_COST",'provision_amount_policy','additional_provision','Total Provision']].sum()
summary['coverage'] = summary['Total Provision'] / summary['NETTOTAL_COST']


# %% [markdown]
# Combinations

# %%
soh_with_combinations = soh.merge(combinations, on=['Std Brand','LOCATION'], how='left')
soh_with_combinations[['s1', 's2', 's3', 's4']]= soh_with_combinations[['s1', 's2', 's3', 's4']].fillna(0)
soh_with_combinations.to_excel(r"Output/aging_provision_combinations.xlsx", index=False)

# %% [markdown]
# Preparation of the entry

# %%
soh_with_combinations['Total Provision'].sum()

# %%
entry = soh_with_combinations.groupby(["s1","s2","s3","s4"])['Total Provision'].sum().reset_index().fillna(0)
entry['s5'] = 63002


# %%
entry['Total Provision'].sum()

# %%
entry2 = entry.copy()
entry2['Total Provision'] = entry2['Total Provision'] * -1
entry2['s5'] = 23993

# %%
completed_entry = pd.concat([entry, entry2], ignore_index=True)
completed_entry.rename(columns={'Total Provision': 'Dr/(CR)'}, inplace=True)
completed_entry = completed_entry[completed_entry['Dr/(CR)'] != 0]

# %%
completed_entry[['s1', 's2', 's3', 's4', 's5','Dr/(CR)']].to_csv(r"Output/completed_entry.csv", index=False)

# %% [markdown]
# difference entry

# %%
diff_table = soh_with_combinations.groupby(["s1","s2","s3","s4"])['Total Provision'].sum().reset_index().fillna(0).merge(existing_balances, on=['s1','s2','s3','s4'], how='outer').fillna(0)

# %%
diff_table['Dr/(CR)'] = (diff_table['Total Provision'] + diff_table['Closing balance'])*-1
diff_table.drop(['Closing balance','Total Provision'], inplace=True,axis=1)

# %%
diff_table['s5'] = 23993

# %%
diff_table2 = diff_table.copy()
diff_table2['Dr/(CR)'] = diff_table2['Dr/(CR)'] * -1
diff_table2['s5'] = 63002

# %%
diff_entry = pd.concat([diff_table, diff_table2], ignore_index=True)
#diff_entry.rename(columns={'Total Provision': 'Dr/(CR)'}, inplace=True)
diff_entry = diff_entry[diff_entry['Dr/(CR)'] != 0]

# %%
diff_entry[['s1', 's2', 's3', 's4', 's5','Dr/(CR)']].to_csv(r"Output/diff_entry.csv", index=False)

# %% [markdown]
# Analysis

# %%
damage_summary = soh_with_combinations[soh_with_combinations['location_catergory'] == 'Damage'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
damage_summary['coverage'] = damage_summary['Total Provision'] / damage_summary['NETTOTAL_COST']
damage_summary

# %%
leftover_summary = soh_with_combinations[soh_with_combinations['location_catergory'] == 'Leftover'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
leftover_summary['coverage'] = leftover_summary['Total Provision'] / leftover_summary['NETTOTAL_COST']
leftover_summary

# %%
closed_summary = soh_with_combinations[soh_with_combinations['Closed_status'] == 'Closed'].groupby('Std Brand')[['NETTOTAL_COST', 'Total Provision']].sum()
closed_summary['coverage'] = closed_summary['Total Provision'] / closed_summary['NETTOTAL_COST']
closed_summary

# %% [markdown]
# checks

# %%
# verify the original seasons in the std buckets 
check_buckets = soh[['season_bucket','std_season' ]].drop_duplicates().sort_values(by='season_bucket', ascending=True)

# %%
# verify the seasons in the correct buckets 
check_season = soh[['std_season', original_season]].drop_duplicates().sort_values(by='std_season', ascending=True)

# %%
#missing combinations in output
missing_combinations = soh_with_combinations[(soh_with_combinations['NETTOTAL_COST'] != 0)&(soh_with_combinations['s1'].isna())] 

# %%
# Check for missing values in key columns
missing_in_std_brand = soh[soh['Std Brand'].isnull()]
print("Net cost of missing std_brand :", missing_in_std_brand['NETTOTAL_COST'].sum())



# %%
# Check for duplicates in mapping [original brand name]
duplicates_mapping = mapping.duplicated(subset=['GROUP_NAME'], keep=False)
print("Duplicate original brand names in mapping:", mapping[duplicates_mapping].shape[0])

# %%
missing_std_brands_in_soh = set(mapping['Std Brand']) - set(soh['Std Brand'])
print("Std Brands in mapping missing in SOH:", missing_std_brands_in_soh)


# %%
# Check for garbage/unknown seasons in std_season
garbage_seasons = soh[(soh['std_season'] == "Unknown")&(~soh['Model'].isin([
        'Consignment',
        'Guaranteed Margin',
        'Buying Pull - Mango'
    ]))]
print("Cost of unknown std_season:", f"{garbage_seasons['NETTOTAL_COST'].sum():,.2f}")

# %%




# Check for missing in combinations merge
missing_comb_rows = soh_with_combinations[soh_with_combinations['s4'] == 0]
print("Cost with combination mapping:", f"{missing_comb_rows['NETTOTAL_COST'].sum():,.2f}")


# %%
soh_with_combinations[soh_with_combinations[original_season].isna() | (soh_with_combinations[original_season] == '')].groupby('Std Brand')['NETTOTAL_COST'].sum()

# %%
completed_entry[completed_entry['s5']==23993]['Dr/(CR)'].sum(), existing_balances.iloc[:,-1].sum(),diff_entry[diff_entry['s5']==23993]['Dr/(CR)'].sum()

# %%
completed_entry[completed_entry['s5']==23993]['Dr/(CR)'].sum(), existing_balances.iloc[:,-1].sum(),diff_entry[diff_entry['s5']==23993]['Dr/(CR)'].sum()

# %%
entry_check = existing_balances.iloc[:,-1].sum()+ diff_entry[diff_entry['s5']==23993]['Dr/(CR)'].sum() - completed_entry[completed_entry['s5']==23993]['Dr/(CR)'].sum()

# %%
print(f"{entry_check=:,.2f}")

# %%



