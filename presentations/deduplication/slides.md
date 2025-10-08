---
theme: seriph
title: Streamlining Project Data for Sales
info: |
    A discussion on project data deduplication and consolidated views for sales efficiency.
class: text-center
mdc: true
---

# Streamlining Project Data for Sales

A discussion on project data deduplication and consolidated views for sales efficiency

<div class="abs-br m-6 text-sm">
  FBM Sales Recommender Initiative
</div>
---

# Current System Behavior and Data Sources

The system currently treats each data point or match as a distinct entry.

*   **Multiple Sources**: Project data is ingested from different providers (ConstructConnect, Dodge). If a project exists in both, it may be duplicated.
*   **Multiple Matches**: A single project can be relevant to various sales initiatives or searches. Each match can create a separate line item.

The objective is to retain all information but present it more effectively.

---

# Challenges in Defining Duplicate Projects

Identifying a unique project across ConstructConnect and Dodge presents several challenges:

*   **Project Name Discrepancies**: A project named "Main Street Tower" in Dodge might be "Main St. Development" in ConstructConnect. How should these be matched?
*   **Location Ambiguity**:
    *   Are projects with identical latitude and longitude always duplicates?
    *   Consider large complexes with multiple buildings at the same address (e.g., phased developments or separate towers on one plot).
*   **Other Identifying Factors**: What other data points (e.g., owner, architect, value, dates) can reliably confirm a match? What is an acceptable variance?

Addressing these complexities is crucial for effective deduplication.

---

# Objective: Consolidated Project View

The goal is to simplify the management and viewing of project information. The ideal state includes:

*   **A single, consolidated record** for each unique real-world project.
*   All relevant details, including **all matched searches** and the **relevance to each search**, accessible in one place.
*   Ultimately, enabling users to **quickly identify and act on opportunities** without processing redundant entries.

---

# Proposed Solution: Consolidated Project Data Views

We are exploring methods to present project data more effectively.

Current View (Multiple Rows per Project):

| Project ID | Source         | Search   | Relevance   | Project Name | Location     | Value    |
|------------|----------------|----------|-------------|--------------|--------------|----------|
| Project A  | ConstructConnect | Drywall  | Very High   | Alpha Tower  | New York, NY | $5M      |
| Project A  | Dodge          | Drywall  | Very High   | Alpha Tower  | New York, NY | $5M      |
| Project A  | ConstructConnect | Ceilings | Moderate    | Alpha Tower  | New York, NY | $5M      |
| Project B  | Dodge          | Drywall  | Low         | Beta Complex | Chicago, IL  | $2M      |

The aim is to display one project per row, with all associated information consolidated.

---

# Option 1: Compact View

This view focuses on critical information, with further details available on click/hover.

| Project Name | Primary Search | Top Relevance | Top Reasoning                          | Location     | Value | Data Sources | Other Matches |
|--------------|----------------|---------------|----------------------------------------|--------------|-------|--------------|---------------|
| Alpha Tower  | Drywall        | Very High     | Key material specs, timeline aligns    | New York, NY | $5M   | CC, Dodge    | Ceilings (Mod) |
| Beta Complex | Drywall        | Low           | Limited scope match                    | Chicago, IL  | $2M   | Dodge        | None          |

*   **Primary Search**: The search term yielding the highest relevance.
*   **Top Relevance**: The highest relevance score for the project.
*   **Top Reasoning**: A brief summary of why the project has its top relevance (e.g., "Key material specs, timeline aligns").
*   **Data Sources**: Indicators for data sources (e.g., ConstructConnect, Dodge).
*   **Other Matches**: A summary of other matched searches (e.g., "Ceilings (Moderate), HVAC (Low)").

---

# Option 1: Compact View - Detail Drill-Down

After clicking on "Alpha Tower" from the Compact View:

**Project Details: Alpha Tower**
-------------------------------------------------
**Project Name**:
  * ConstructConnect: Alpha Tower (CRM: arb_project_name)
  * Dodge: Alpha Project - Phase 1 (CRM: arb_project_name)

**Location**: New York, NY (CRM: arb_project_city, arb_project_stateorprovince)

**Value**: $5M (CRM: estimatedamount)

**Data Sources**: ConstructConnect, Dodge
-------------------------------------------------
**Matched Searches & Relevance:**
*   **Drywall**:
    *   Relevance: Very High
    *   Reasoning: Key material specifications match, large square footage. Project timeline aligns with Q3 targets.
*   **Ceilings**:
    *   Relevance: Moderate
    *   Reasoning: Secondary scope of work identified. Potential for up-sell.
-------------------------------------------------
**Additional Project Information (Consolidated from CC/Dodge, mapped to CRM):**
*   **External Project ID**: 
    *   ConstructConnect: 789123 (CRM: fbm_externalleadid)
    *   Dodge: D456789 (CRM: fbm_externalleadid) 
*   **Project Stage**: 
    *   ConstructConnect: Bidding Phase (CRM: fbm_projectstage)
    *   Dodge: Planning (CRM: fbm_projectstage)
*   **Bid Date**: 2025-07-15 (CRM: fbm_biddate) *(Likely consistent or one primary date)*
*   **Estimated Start Date**: 2025-09-01 (CRM: fbm_startdate) *(Likely consistent or one primary date)*
*   **Project Address Line 1**: 123 Main Street (CRM: arb_project_line1) *(High chance of consistency)*
*   **Project Postal Code**: 10001 (CRM: arb_project_postalcode) *(High chance of consistency)*
*   **Project Longitude**: -73.985130 (CRM: fbm_project_address_long) *(High chance of consistency)*
*   **Project Latitude**: 40.748817 (CRM: fbm_project_address_lat) *(High chance of consistency)*

-------------------------------------------------

**Additional Project Information (Consolidated from CC/Dodge, mapped to CRM):**
*   **Project Description**: 
    *   ConstructConnect: Multi-story commercial tower... (CRM: fbm_projectdescription)
    *   Dodge: New 20-floor office building... (CRM: fbm_projectdescription)
*   **Project Categories**: 
    *   ConstructConnect: Commercial, High-Rise... (CRM: fbm_projectcategories)
    *   Dodge: Office Buildings, New Construction... (CRM: fbm_projectcategories)
*   **Owner**: Global Real Estate Corp (Potentially from contacts/companies linked to project)
*   **Architect**: Innovative Designs LLC (Potentially from contacts/companies linked to project)
---

# Option 2: Expanded View

This view shows more details directly in the main table, potentially using wrapped text or wider rows.

| Project Name | Location     | Value | Data Sources | Matched Searches & Relevance                     |
|--------------|--------------|-------|--------------|--------------------------------------------------|
| Alpha Tower  | New York, NY | $5M   | CC, Dodge    | Drywall (Very High, Reason: XYZ), Ceilings (Moderate, Reason: ABC) |
| Beta Complex | Chicago, IL  | $2M   | Dodge        | Drywall (Low, Reason: PQR)                       |

*   **Matched Searches & Relevance**: Lists each search term the project matched, its relevance level, and potentially a reasoning snippet. This field could be scrollable if content is extensive.

---

# Discussion Points for Feedback

Your input is essential to refine this concept. Please consider the following:

*   How do you currently manage projects that appear multiple times? What are the primary frustrations?
*   Would a single view for each project, displaying all its matches (e.g., "Drywall - Very High," "Ceilings - Moderate"), be more effective?
*   What information is critical to include in this consolidated view?
*   How would this change impact your daily tasks and decision-making processes?
*   What are your concerns? What features would make this system most useful?

*(Feedback will also be gathered from other end-users.)*

---

# Next Steps

Based on this discussion:

1.  **Gather Initial Stakeholder Insights**: Understand needs and preferences from this meeting.
2.  **Collect Broader User Feedback**: Engage with other sales team members.
3.  **Refine Solution Concept**: Adjust the proposed solution based on all feedback.
4.  **Technical Feasibility Assessment**: Investigate implementation options for the refined solution.
5.  **Develop & Test**: Build and test the new system with ongoing user involvement.

The objective is to develop a tool that effectively supports sales operations.
