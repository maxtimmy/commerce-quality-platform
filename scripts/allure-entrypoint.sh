#!/bin/sh
set -eu

if [ "${1:-}" = "generate" ] && [ "${2:-}" = "/allure-results" ]; then
    merged_dir=/tmp/allure-results
    mkdir -p "$merged_dir"
    find /allure-results -type f -exec cp -f {} "$merged_dir" \;
    if [ -f "$merged_dir/environment.properties" ]; then
        sed -i 's/^run=.*/run=combined local report/' "$merged_dir/environment.properties"
        sed -i 's/^browser=.*/browser=chromium, firefox, webkit/' "$merged_dir/environment.properties"
        printf '%s\n' 'suites=smoke, regression, contract, ui' >> "$merged_dir/environment.properties"
    fi
    shift 2
    set -- generate "$merged_dir" "$@"
fi

exec allure "$@"
