#!/usr/bin/env python3
"""
Main test suite for the Hipocrate API
"""
import asyncio
import aiohttp
import os
import argparse
import sys
import unittest

# Import test functions from separate modules
from tests.root import test_root_endpoint
from tests.auth import test_basic_auth_success, test_basic_auth_missing_credentials, test_basic_auth_invalid_credentials
from tests.patients import test_patient_search_endpoint, test_invalid_patient_search, test_patient_endpoint_missing_id
from tests.analyses import test_observations_endpoint_missing_patient_id
from tests.reports import test_diagnostic_report_endpoint_missing_id
from tests.checkout import test_encounter_endpoint_missing_id, test_encounter_endpoint_known_id
from tests.checkin import test_checkin_endpoint_missing_id, test_checkin_endpoint_known_id
from tests.checkup import test_checkup_endpoint_missing_id, test_checkup_endpoint_known_id
from tests.cnp import test_cnp_validation_endpoint, test_cnp_validation_missing_id
from tests.worklist import (TestNameToDicom, TestBuildDatasets,
                             TestWorklistCache, TestWorklistSCP)
from tests.extractors import test_extract_text_after_label_basic, test_extract_text_after_label_with_element_tag, test_extract_text_after_label_with_stop_at, test_extract_text_after_label_not_found, test_extract_text_after_label_case_insensitive, test_extract_text_with_bold_tag, test_extract_text_with_bold_and_underline_tags, test_extract_text_with_whitespace, test_extract_id_from_link_basic, test_extract_id_from_link_with_custom_pattern, test_extract_id_from_link_no_href, test_extract_id_from_link_no_match, test_extract_ids_from_links_basic, test_extract_ids_from_links_with_custom_pattern, test_extract_ids_from_links_no_matches
from tests.hippo_data import TestHippoData
from tests.markdown import TestMarkdownConversion
from tests.llm_client import TestProviderSelection, TestPromptRegistry

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

# Group tests by functionality
TEST_GROUPS = {
    "all": [
        test_root_endpoint,
        test_basic_auth_success,
        test_basic_auth_missing_credentials,
        test_basic_auth_invalid_credentials,
        test_patient_search_endpoint,
        test_invalid_patient_search,
        test_patient_endpoint_missing_id,
        test_observations_endpoint_missing_patient_id,
        test_diagnostic_report_endpoint_missing_id,
        test_encounter_endpoint_missing_id,
        test_encounter_endpoint_known_id,
        test_checkin_endpoint_missing_id,
        test_checkin_endpoint_known_id,
        test_checkup_endpoint_missing_id,
        test_checkup_endpoint_known_id,
        test_cnp_validation_endpoint,
        test_cnp_validation_missing_id,
        test_extract_text_after_label_basic,
        test_extract_text_after_label_with_element_tag,
        test_extract_text_after_label_with_stop_at,
        test_extract_text_after_label_not_found,
        test_extract_text_after_label_case_insensitive,
        TestHippoData,
        TestMarkdownConversion,
        TestProviderSelection,
        TestPromptRegistry,
    ],
    "root": [test_root_endpoint],
    "auth": [
        test_basic_auth_success,
        test_basic_auth_missing_credentials,
        test_basic_auth_invalid_credentials
    ],
    "patients": [
        test_patient_search_endpoint,
        test_invalid_patient_search,
        test_patient_endpoint_missing_id
    ],
    "analyses": [test_observations_endpoint_missing_patient_id],
    "reports": [test_diagnostic_report_endpoint_missing_id],
    "checkout": [test_encounter_endpoint_missing_id, test_encounter_endpoint_known_id],
    "checkin": [test_checkin_endpoint_missing_id, test_checkin_endpoint_known_id],
    "checkup": [test_checkup_endpoint_missing_id, test_checkup_endpoint_known_id],
    "cnp": [
        test_cnp_validation_endpoint,
        test_cnp_validation_missing_id
    ],
    "extractors": [
        test_extract_text_after_label_basic,
        test_extract_text_after_label_with_element_tag,
        test_extract_text_after_label_with_stop_at,
        test_extract_text_after_label_not_found,
        test_extract_text_after_label_case_insensitive,
        test_extract_text_with_bold_tag,
        test_extract_text_with_bold_and_underline_tags,
        test_extract_text_with_whitespace,
        test_extract_id_from_link_basic,
        test_extract_id_from_link_with_custom_pattern,
        test_extract_id_from_link_no_href,
        test_extract_id_from_link_no_match,
        test_extract_ids_from_links_basic,
        test_extract_ids_from_links_with_custom_pattern,
        test_extract_ids_from_links_no_matches
    ],
    "hippodata": [TestHippoData],
    "markdown": [TestMarkdownConversion],
    "worklist": [TestNameToDicom, TestBuildDatasets, TestWorklistCache, TestWorklistSCP],
    "llm": [
        TestProviderSelection,
        TestPromptRegistry,
    ],
}

async def run_tests(test_list) -> None:
    """Run specified API tests"""
    print(f"Starting API tests against {BASE_URL}")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        results = []
        for test in test_list:
            try:
                from io import StringIO
                # Check for unittest.TestCase subclass first (classes are also callable)
                if isinstance(test, type) and issubclass(test, unittest.TestCase):
                    suite = unittest.TestLoader().loadTestsFromTestCase(test)
                    test_output = StringIO()
                    runner = unittest.TextTestRunner(stream=test_output, verbosity=2)
                    test_result = runner.run(suite)
                    success = test_result.wasSuccessful()
                    results.append(success)
                    test_name = test.__name__
                    print(f"Test {test_name}: {'PASS' if success else 'FAIL'}")
                    if not success:
                        print(test_output.getvalue())
                else:
                    # Regular async test function
                    result = await test(session)
                    results.append(result)
            except Exception as e:
                # Safely get test name for error reporting
                test_name = getattr(test, '__name__', str(test))
                print(f"Test {test_name} failed with exception: {e}")
                results.append(False)
            print()
        
        # Summary
        passed = sum(results)
        total = len(results)
        print("=" * 50)
        print(f"Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("All tests passed! 🎉")
        else:
            print(f"{total - passed} tests failed. ❌")

def main():
    parser = argparse.ArgumentParser(description="Run Hipocrate API tests")
    parser.add_argument(
        "test_group", 
        nargs="?", 
        default="all",
        choices=list(TEST_GROUPS.keys()),
        help="Test group to run (default: all)"
    )
    
    args = parser.parse_args()
    
    if args.test_group not in TEST_GROUPS:
        print(f"Error: Unknown test group '{args.test_group}'")
        print(f"Available groups: {', '.join(TEST_GROUPS.keys())}")
        sys.exit(1)
    
    test_list = TEST_GROUPS[args.test_group]
    print(f"Running {args.test_group} tests ({len(test_list)} tests)")
    
    asyncio.run(run_tests(test_list))

if __name__ == "__main__":
    main()
