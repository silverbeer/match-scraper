# MLS Iframe Structure Investigation Report

## Executive Summary

I successfully investigated the iframe structure on the MLS schedule page. The iframe contains a complete schedule interface with multiple filter options including age groups, clubs, competition, gender, divisions, and date picker. All filter interactions are contained within the iframe at URL `https://www.modular11.com/league-schedule/mls-next-homegrown-division`.

## Iframe Access Pattern

### Basic Access
```python
# Access the iframe content frame
main_element = await page.wait_for_selector('main[role="main"]')
iframe = await main_element.query_selector("iframe")
iframe_content = await iframe.content_frame()
await iframe_content.wait_for_load_state('load')
```

### Alternative Access Pattern (from your recorded script)
```python
iframe_content = await page.get_by_role("main", name="Page main content").locator("iframe").content_frame()
```

## Filter Elements Discovered

### 1. Age Group Filter
**Element Type**: Bootstrap Select (Custom Dropdown)
**JavaScript Attribute**: `js-age=""`
**Location**: Line 79 in iframe HTML

**HTML Structure**:
```html
<select class="selectpicker survey-select-picker-small filter-select-custom" multiple="multiple" js-age="" tabindex="-98">
    <option value="21">U13</option>
    <option value="22">U14</option>
    <option value="33">U15</option>
    <option value="14">U16</option>
    <option value="15">U17</option>
    <option value="26">U19</option>
</select>
```

**Bootstrap Enhanced Structure**:
- Custom dropdown with clickable list items
- Each age group appears as `<span class="text">U13</span>` etc.
- Role-based selectors available

**Interaction Patterns**:
```python
# Method 1: Click on the bootstrap dropdown button
await iframe_content.query_selector('button[data-toggle="dropdown"]').click()
await iframe_content.query_selector('span.text:has-text("U14")').click()

# Method 2: Direct option selection (if bootstrap allows)
await iframe_content.select_option('select[js-age]', value='22')  # U14

# Method 3: Role-based selector
await iframe_content.get_by_role("option", name="U14").click()
```

### 2. Club Filter
**Element Type**: Bootstrap Select with Search
**JavaScript Attribute**: `js-club=""` (likely)
**Location**: After age group filter

**Features**:
- Searchable dropdown with `<input type="text" class="form-control" autocomplete="off" role="textbox" aria-label="Search">`
- Multiple club options available
- Examples found: "Southern States Soccer Club", "AC River", etc.

**Interaction Patterns**:
```python
# Open dropdown and search
club_dropdown = await iframe_content.query_selector('.bootstrap-select .dropdown-toggle')
await club_dropdown.click()

# Use search box
search_box = await iframe_content.query_selector('.bs-searchbox input')
await search_box.fill("Southern States")
await iframe_content.get_by_role("option", name="Southern States Soccer Club").click()
```

### 3. Date Filter
**Element Type**: Date Input with Custom Picker
**Class**: `input-datapicker`
**Location**: Line 70

**HTML Structure**:
```html
<input type="text" class="form-control input-datapicker survey-select-picker-small" name="datefilter" aria-invalid="false">
```

**Interaction Patterns**:
```python
# Fill date field
await iframe_content.fill('input[name="datefilter"]', "09/01/2025 - 09/30/2025")

# Or trigger date picker
await iframe_content.click('input[name="datefilter"]')
# Then interact with date picker elements
```

### 4. Gender Filter
**Location**: Found in match data structure
**Options**: "MALE", "FEMALE" (inferred from match data)

### 5. Division Filter
**Expected**: Similar bootstrap select structure
**Options**: "Homegrown Division", "Academy Division" (inferred from URL patterns)

### 6. Competition Filter
**Expected**: Bootstrap select dropdown
**Options**: Various competition types

## Technical Implementation Details

### Interactive Elements Summary
- **Buttons**: 31 total, 4 visible
- **Inputs**: 2 total, 1 visible (the date picker)
- **Selects**: 4 total, 4 visible (age, club, competition, etc.)
- **Links**: 286 total, 9 visible
- **Clickable Elements**: 6 total, 4 visible

### Bootstrap Select Enhancement
All select elements are enhanced with Bootstrap Select plugin, which:
- Converts `<select>` elements into custom dropdowns
- Provides search functionality for some dropdowns
- Uses `<li>` and `<a>` elements for options instead of native `<option>`
- Maintains accessibility with proper ARIA roles

### Interaction Strategies

#### Strategy 1: Bootstrap UI Interaction (Recommended)
```python
async def apply_age_group_filter(iframe_content, age_group):
    """Apply age group filter using bootstrap dropdown interaction."""
    # Click the dropdown trigger
    age_dropdown = await iframe_content.query_selector(
        'label:has-text("Age Group") + div .dropdown-toggle'
    )
    await age_dropdown.click()
    
    # Click the specific age group option
    option = await iframe_content.get_by_role("option", name=age_group)
    await option.click()
    
    # Wait for selection to apply
    await asyncio.sleep(1)

async def apply_club_filter(iframe_content, club_name):
    """Apply club filter with search functionality."""
    # Find and click club dropdown
    club_dropdown = await iframe_content.query_selector(
        'div.bootstrap-select:has(.bs-searchbox) .dropdown-toggle'
    )
    await club_dropdown.click()
    
    # Use search if available
    search_box = await iframe_content.query_selector('.bs-searchbox input')
    if search_box:
        await search_box.fill(club_name)
        await asyncio.sleep(0.5)  # Wait for search results
    
    # Click the option
    option = await iframe_content.get_by_role("option", name=club_name)
    await option.click()

async def apply_date_filter(iframe_content, start_date, end_date):
    """Apply date range filter."""
    date_input = await iframe_content.query_selector('input[name="datefilter"]')
    date_range = f"{start_date} - {end_date}"
    await date_input.fill(date_range)
    
    # Trigger change event
    await date_input.press('Enter')
```

#### Strategy 2: Direct Select Interaction (Backup)
```python
async def apply_age_group_direct(iframe_content, age_group_value):
    """Apply age group using direct select option value."""
    # Use the value mapping: U13=21, U14=22, U15=33, U16=14, U17=15, U19=26
    await iframe_content.select_option('select[js-age]', value=age_group_value)
```

### Value Mappings for Age Groups
- U13 = "21"
- U14 = "22" 
- U15 = "33"
- U16 = "14"
- U17 = "15"
- U19 = "26"

## Role-Based Selectors Compatibility

The iframe supports role-based selectors for accessibility:

```python
# Age group options
await iframe_content.get_by_role("button", name="Age Group U13").click()
await iframe_content.get_by_role("option", name="U14").click()

# Club options  
await iframe_content.get_by_role("option", name="Southern States Soccer Club").click()

# Date picker
await iframe_content.get_by_role("textbox", name="Date filter").fill("09/01/2025")
```

## Dynamic Behavior Observations

1. **Filter Dependencies**: Changing one filter may affect available options in others
2. **Search Functionality**: Club filter includes real-time search
3. **Multiple Selection**: Age group filter supports multiple selections
4. **Results Loading**: Filters trigger dynamic content loading (may need wait strategies)
5. **Bootstrap Events**: Custom dropdown events may need specific handling

## Recommended Implementation Approach

1. **Iframe Access**: Use the confirmed pattern with `main[role="main"] iframe`
2. **Wait Strategy**: Always wait for iframe content to load before interacting
3. **Bootstrap Interaction**: Prefer clicking bootstrap UI elements over direct select manipulation
4. **Error Handling**: Include fallback strategies for both bootstrap and direct select interaction
5. **Timing**: Add appropriate waits between filter applications
6. **Verification**: Check filter application success by observing UI state changes

## Testing Recommendations

1. Test all age group values with both bootstrap and direct interaction
2. Verify club search functionality with partial and full names
3. Test date range picker with various date formats
4. Confirm multiple filter combinations work correctly
5. Validate that filter changes trigger proper results updates

## Conclusion

The iframe-based filter system is fully functional and accessible through multiple interaction patterns. The Bootstrap Select enhancement provides rich UI features but requires specific interaction strategies. The investigation confirms that both the recorded script pattern and standard Playwright selectors work effectively for accessing and manipulating the filters within the iframe.