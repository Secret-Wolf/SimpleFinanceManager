// Profiles Module (deprecated - replaced by households)
// Stub functions to prevent JS errors from legacy references

let profiles = [];

async function loadProfilesData() {
    profiles = [];
}

async function loadProfilesDropdown() {
    // No-op: profile selector removed
}

function onProfileFilterChange() {
    // No-op
}

async function loadProfileManagement() {
    // Redirect to households
    navigateTo('households');
}
