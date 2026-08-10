import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { canonicalizePath } from "../utils/canonicalizePath";

/**
 * Client 301-equivalent: strip trailing slash from pathname (БЗ canonical).
 */
export function StripTrailingSlash() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const { pathname, search, hash } = location;
    if (pathname !== "/" && pathname.endsWith("/")) {
      const next = canonicalizePath(pathname);
      navigate(`${next}${search}${hash}`, { replace: true });
    }
  }, [location, navigate]);

  return null;
}
