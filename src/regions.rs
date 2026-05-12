use crate::errors::{Result, ZohoError};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Region {
    pub code: &'static str,
    pub accounts_url: &'static str,
    pub api_url: &'static str,
}

const REGIONS: &[Region] = &[
    Region {
        code: "us",
        accounts_url: "https://accounts.zoho.com",
        api_url: "https://www.zohoapis.com",
    },
    Region {
        code: "eu",
        accounts_url: "https://accounts.zoho.eu",
        api_url: "https://www.zohoapis.eu",
    },
    Region {
        code: "in",
        accounts_url: "https://accounts.zoho.in",
        api_url: "https://www.zohoapis.in",
    },
    Region {
        code: "au",
        accounts_url: "https://accounts.zoho.com.au",
        api_url: "https://www.zohoapis.com.au",
    },
    Region {
        code: "jp",
        accounts_url: "https://accounts.zoho.jp",
        api_url: "https://www.zohoapis.jp",
    },
    Region {
        code: "ca",
        accounts_url: "https://accounts.zohocloud.ca",
        api_url: "https://www.zohoapis.ca",
    },
    Region {
        code: "sa",
        accounts_url: "https://accounts.zoho.sa",
        api_url: "https://www.zohoapis.sa",
    },
];

pub fn resolve(code: &str) -> Result<&'static Region> {
    let normalized = code.trim().to_ascii_lowercase();
    let key = if normalized.is_empty() {
        "us"
    } else {
        &normalized
    };
    REGIONS.iter().find(|r| r.code == key).ok_or_else(|| {
        let valid: Vec<&str> = {
            let mut codes: Vec<&str> = REGIONS.iter().map(|r| r.code).collect();
            codes.sort_unstable();
            codes
        };
        ZohoError::validation(format!(
            "Unknown region '{key}'. Valid: {}",
            valid.join(", ")
        ))
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_known_regions() {
        assert_eq!(resolve("us").unwrap().api_url, "https://www.zohoapis.com");
        assert_eq!(resolve("eu").unwrap().api_url, "https://www.zohoapis.eu");
        assert_eq!(resolve("in").unwrap().api_url, "https://www.zohoapis.in");
        assert_eq!(
            resolve("au").unwrap().api_url,
            "https://www.zohoapis.com.au"
        );
        assert_eq!(resolve("jp").unwrap().api_url, "https://www.zohoapis.jp");
        assert_eq!(resolve("ca").unwrap().api_url, "https://www.zohoapis.ca");
        assert_eq!(resolve("sa").unwrap().api_url, "https://www.zohoapis.sa");
    }

    #[test]
    fn resolve_normalises_input() {
        assert_eq!(resolve("US").unwrap().code, "us");
        assert_eq!(resolve("  Eu  ").unwrap().code, "eu");
        assert_eq!(resolve("\tIN\n").unwrap().code, "in");
    }

    #[test]
    fn empty_defaults_to_us() {
        assert_eq!(resolve("").unwrap().code, "us");
        assert_eq!(resolve("   ").unwrap().code, "us");
    }

    #[test]
    fn unknown_returns_validation_error() {
        let err = resolve("zz").unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains("zz"));
        // valid list is sorted
        assert!(err.message.contains("au, ca, eu, in, jp, sa, us"));
    }

    #[test]
    fn accounts_urls_match_python_mapping() {
        assert_eq!(
            resolve("us").unwrap().accounts_url,
            "https://accounts.zoho.com"
        );
        assert_eq!(
            resolve("ca").unwrap().accounts_url,
            "https://accounts.zohocloud.ca"
        );
    }
}
