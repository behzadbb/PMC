"""
PMC Article Scraper
Extracts article metadata, abstract, full text, and other information from PMC articles.
"""

import json
import os
import re
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Union
from urllib.parse import urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

from DTO.Article import Article

# Optional Selenium imports (used as a fallback when HTTP is blocked)
try:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService
    from webdriver_manager.firefox import GeckoDriverManager

    _SELENIUM_AVAILABLE = True
except Exception:
    _SELENIUM_AVAILABLE = False

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore')


class PMCScraper:
    def __init__(self, cache_file: str = 'pmc_session_cache.json'):
        """
        Initialize PMC scraper with session caching.
        
        Args:
            cache_file: Path to file for storing cookies and headers cache
        """
        self.cache_file = cache_file
        self.session = requests.Session()
        self._selenium_driver = None  # Reuse driver across requests
        
        # Try to load cached cookies and headers
        if self._load_session_cache():
            print("Loaded cookies and headers from cache")
        else:
            # Initialize with default headers
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0'
            })
    
    def __del__(self):
        """Cleanup: close Selenium driver if it exists."""
        if self._selenium_driver:
            try:
                self._selenium_driver.quit()
            except:
                pass
    
    def _load_session_cache(self) -> bool:
        """
        Load cookies and headers from cache file.
        
        Returns:
            True if cache was loaded successfully, False otherwise
        """
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # Load headers
                if 'headers' in cache_data:
                    self.session.headers.update(cache_data['headers'])
                
                # Load cookies
                if 'cookies' in cache_data:
                    for cookie in cache_data['cookies']:
                        # Create a cookie object
                        self.session.cookies.set(
                            cookie.get('name'),
                            cookie.get('value'),
                            domain=cookie.get('domain'),
                            path=cookie.get('path', '/'),
                        )
                
                return True
        except Exception as e:
            print(f"Warning: Could not load session cache: {e}")
        
        return False
    
    def _save_session_cache(self) -> bool:
        """
        Save current cookies and headers to cache file.
        
        Returns:
            True if cache was saved successfully, False otherwise
        """
        try:
            cache_data = {
                'headers': dict(self.session.headers),
                'cookies': []
            }
            
            # Extract cookies
            for cookie in self.session.cookies:
                cache_data['cookies'].append({
                    'name': cookie.name,
                    'value': cookie.value,
                    'domain': cookie.domain,
                    'path': cookie.path,
                })
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            print(f"Saved cookies and headers to {self.cache_file}")
            return True
        except Exception as e:
            print(f"Warning: Could not save session cache: {e}")
            return False
    
    def _refresh_session_from_selenium(self, url: str = "https://pmc.ncbi.nlm.nih.gov/") -> bool:
        """
        Use Selenium to get fresh cookies and headers, then update session cache.
        Reuses existing driver if available to avoid rate limits.
        
        Args:
            url: URL to visit for getting cookies (default: PMC homepage)
        
        Returns:
            True if successful, False otherwise
        """
        if not _SELENIUM_AVAILABLE:
            print("Selenium is not available, cannot refresh session")
            return False
        
        try:
            print("Refreshing cookies and headers using Selenium...")
            
            # Reuse existing driver if available
            if self._selenium_driver is None:
                driver = self._get_selenium_driver()
                if driver is None:
                    return False
                self._selenium_driver = driver
            else:
                driver = self._selenium_driver
            
            # Visit PMC homepage to get cookies
            driver.get(url)
            driver.implicitly_wait(5)
            
            # Update session with cookies from Selenium
            self._update_session_from_selenium(driver)
            
            # Save to cache
            self._save_session_cache()
            
            print("Successfully refreshed session from Selenium")
            return True
        except Exception as e:
            print(f"Error refreshing session from Selenium: {e}")
            # If driver failed, reset it
            if self._selenium_driver:
                try:
                    self._selenium_driver.quit()
                except:
                    pass
                self._selenium_driver = None
            return False
    
    def save_to_json(self, article_data: Union[Article, Dict], output_dir: str = 'articles') -> str:
        """
        Save article data to JSON file with PMCID as filename.
        
        Args:
            article_data: Article instance or Dictionary containing article data
            output_dir: Directory to save the file (default: 'articles')
        
        Returns:
            Path to the saved JSON file
        """
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert Article instance to dict if needed
        if isinstance(article_data, Article):
            # Support both Pydantic v1 and v2
            try:
                data_dict = article_data.model_dump(exclude_none=False)  # Pydantic v2
            except AttributeError:
                data_dict = article_data.dict(exclude_none=False)  # Pydantic v1
            pmcid = article_data.PMCID
        else:
            data_dict = article_data
            pmcid = article_data.get('pmcid') or article_data.get('PMCID', 'unknown')
        
        if pmcid and pmcid != 'unknown':
            filename = f"{pmcid}.json"
        else:
            # Fallback: try to extract from URL
            url = data_dict.get('url', '')
            pmcid_match = re.search(r'PMC(\d+)', url)
            if pmcid_match:
                filename = f"PMC{pmcid_match.group(1)}.json"
            else:
                filename = 'pmc_article_data.json'
        
        output_path = os.path.join(output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_dict, f, indent=2, ensure_ascii=False)
        
        return output_path
    
    def scrape_from_file(self, file_path: str, url: str = None) -> Union[Article, Dict]:
        """
        Scrape article data from a saved HTML file.
        
        Args:
            file_path: Path to the HTML file
            url: Optional URL for the article
        
        Returns:
            Article instance containing all extracted article data, or Dict with error if failed
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'lxml')
            
            # Extract PMCID from content or URL
            pmcid = None
            if url:
                pmcid_match = re.search(r'PMC(\d+)', url)
                if pmcid_match:
                    pmcid = pmcid_match.group(1)
            
            if not pmcid:
                pmcid_match = re.search(r'PMC(\d+)', content)
                if pmcid_match:
                    pmcid = pmcid_match.group(1)
            
            if not pmcid:
                return {'error': 'Could not extract PMCID', 'file': file_path}
            
            result = self._extract_from_html(soup, url or file_path, pmcid)
            return self._create_article_instance(result)
            
        except Exception as e:
            return {'error': str(e), 'file': file_path}
    
    def scrape_article(self, url: str) -> Union[Article, Dict]:
        """
        Scrape a PMC article from the given URL.
        
        Args:
            url: PMC article URL (e.g., https://pmc.ncbi.nlm.nih.gov/articles/PMC4049904/)
        
        Returns:
            Article instance containing all extracted article data, or Dict with error if failed
        """
        try:
            # Extract PMCID from URL
            pmcid_match = re.search(r'PMC(\d+)', url)
            if not pmcid_match:
                return {'error': 'Could not extract PMCID from URL', 'url': url}
            
            pmcid = pmcid_match.group(1)
            
            # Try multiple approaches to get the article data
            errors = []
            session_refreshed = False
            
            # Approach 1: Try HTML page (even if 403, sometimes content is there)
            try:
                response = self.session.get(url, timeout=30, allow_redirects=True, verify=False)
                # Try to parse even if status is not 200
                if response.content and len(response.content) > 1000:  # If we got substantial content
                    soup = BeautifulSoup(response.content, 'lxml')
                    result = self._extract_from_html(soup, url, pmcid)
                    if result.get('title'):  # If we got meaningful data
                        # Save session cache after successful request
                        self._save_session_cache()
                        return self._create_article_instance(result)
                
                # If we got 403 or other access errors, try refreshing session only once
                if response.status_code in [403, 401] and not session_refreshed:
                    if self._selenium_driver is None and _SELENIUM_AVAILABLE:
                        # Only refresh if we don't have a driver yet
                        if self._refresh_session_from_selenium():
                            session_refreshed = True
                            # Retry the request
                            response = self.session.get(url, timeout=30, allow_redirects=True, verify=False)
                            if response.status_code == 200 and response.content and len(response.content) > 1000:
                                soup = BeautifulSoup(response.content, 'lxml')
                                result = self._extract_from_html(soup, url, pmcid)
                                if result.get('title'):
                                    return self._create_article_instance(result)
                
                if response.status_code != 200:
                    errors.append(f"HTML approach: Status {response.status_code}, Content length: {len(response.content) if response.content else 0}")
            except Exception as e:
                errors.append(f"HTML approach: {str(e)}")
            
            # Approach 2: Try XML version (often more accessible)
            xml_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/?report=xml"
            try:
                response = self.session.get(xml_url, timeout=30, verify=False)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    result = self._extract_from_xml(soup, url, pmcid)
                    if result.get('title'):  # If we got meaningful data
                        return self._create_article_instance(result)
                else:
                    errors.append(f"XML approach: Status {response.status_code}")
            except Exception as e:
                errors.append(f"XML approach: {str(e)}")
            
            # Approach 3: Try PMC FTP XML (alternative format)
            ftp_xml_url = f"https://ftp.ncbi.nlm.nih.gov/pub/pmc/{pmcid[:3]}/PMC{pmcid}.xml"
            try:
                response = self.session.get(ftp_xml_url, timeout=30, verify=False)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    result = self._extract_from_xml(soup, url, pmcid)
                    if result.get('title'):
                        return self._create_article_instance(result)
                else:
                    errors.append(f"FTP XML approach: Status {response.status_code}")
            except Exception as e:
                errors.append(f"FTP XML approach: {str(e)}")
            
            # Approach 4: Try using NCBI E-utilities API (official API)
            try:
                # First get PMID from PMC ID
                esummary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id={pmcid}"
                summary_response = self.session.get(esummary_url, timeout=30, verify=False)
                if summary_response.status_code == 200:
                    # Try to get full text via PMC API
                    pmc_api_url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC{pmcid}"
                    api_response = self.session.get(pmc_api_url, timeout=30, verify=False)
                    if api_response.status_code == 200:
                        soup = BeautifulSoup(api_response.content, 'xml')
                        result = self._extract_from_xml(soup, url, pmcid)
                        if result.get('title'):
                            return self._create_article_instance(result)
            except Exception as e:
                errors.append(f"E-utilities API: {str(e)}")
            
            # Approach 5: Try PMC OAI-PMH endpoint (designed for programmatic access)
            try:
                oai_url = f"https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmcid}&metadataPrefix=pmc"
                oai_response = self.session.get(oai_url, timeout=30, verify=False)
                if oai_response.status_code == 200:
                    soup = BeautifulSoup(oai_response.content, 'xml')
                    # OAI response has nested structure
                    record = soup.find('record')
                    if record:
                        metadata = record.find('metadata')
                        if metadata:
                            article = metadata.find('article')
                            if article:
                                result = self._extract_from_xml(article, url, pmcid)
                                if result.get('title'):
                                    return self._create_article_instance(result)
            except Exception as e:
                errors.append(f"OAI-PMH: {str(e)}")

            # Approach 6: Try Selenium (headless Firefox) to get real browser HTML & cookies
            if _SELENIUM_AVAILABLE:
                try:
                    result = self._scrape_with_selenium(url, pmcid)
                    if result and result.get('title'):
                        return self._create_article_instance(result)
                except Exception as e:
                    errors.append(f"Selenium (Firefox): {str(e)}")
            else:
                errors.append("Selenium (Firefox): not available (package not installed or import failed)")

            # Approach 7: Try using requests directly (bypass session)
            try:
                response = requests.get(url, headers=self.session.headers, timeout=30, verify=False)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'lxml')
                    result = self._extract_from_html(soup, url, pmcid)
                    if result.get('title'):
                        return self._create_article_instance(result)
            except Exception as e:
                errors.append(f"Direct requests: {str(e)}")
            
            # If all approaches fail, return error with details
            return {
                'error': 'Could not access article using any method',
                'url': url,
                'attempted_methods': errors
            }
            
        except Exception as e:
            return {'error': str(e), 'url': url}
    
    @staticmethod
    def _parse_publication_date_str(s: str) -> Optional[datetime]:
        """Parse publication date string (e.g. '2013 Nov 5') to datetime for Article DTO."""
        if not s or not s.strip():
            return None
        s = s.strip()
        for fmt in ('%Y %b %d', '%Y %B %d', '%Y-%m-%d', '%Y %m %d', '%Y'):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        year_match = re.search(r'\b(19|20)\d{2}\b', s)
        if year_match:
            try:
                return datetime(int(year_match.group(0)), 1, 1)
            except (ValueError, TypeError):
                pass
        return None
    
    def _create_article_instance(self, article_data: Dict) -> Union[Article, Dict]:
        """
        Convert dictionary to Article instance.
        
        Args:
            article_data: Dictionary containing article data
        
        Returns:
            Article instance or dict with _article_creation_error on validation failure
        """
        data = dict(article_data)
        try:
            # Normalize pmcid: Article expects int (e.g. 4049904), scraper may pass "PMC4049904"
            if data.get('pmcid') is not None:
                raw = data['pmcid']
                if isinstance(raw, str):
                    num = raw.replace('PMC', '').strip()
                    if num.isdigit():
                        data['pmcid'] = int(num)
                elif not isinstance(raw, int):
                    data['pmcid'] = None
            # Normalize publication_date: Article expects datetime or None, scraper may pass "2013 Nov 5"
            if data.get('publication_date') is not None and isinstance(data['publication_date'], str):
                data['publication_date'] = self._parse_publication_date_str(data['publication_date'])
            # Convert references list of dicts to list of strings if needed
            if data.get('references'):
                refs = data['references']
                if isinstance(refs, list) and refs and isinstance(refs[0], dict):
                    data['references'] = [ref.get('text', str(ref)) for ref in refs]
            return Article(**data)
        except Exception as e:
            data['_article_creation_error'] = str(e)
            return data
    
    def _extract_from_html(self, soup: BeautifulSoup, url: str, pmcid: str) -> Dict:
        """Extract data from HTML page."""
        publication_date = self._extract_publication_date(soup)
        article_data = {
            'url': url,
            'doi': self._extract_doi(soup),
            'publication_date': publication_date,
            'year': self._extract_year(soup, publication_date),
            'volume': self._extract_volume(soup),
            'issue': self._extract_issue(soup),
            'type': self._extract_type(soup),
            'title': self._extract_title(soup),
            'authors': self._extract_authors(soup),
            'pmcid': f"PMC{pmcid}",
            'pmid': self._extract_pmid(soup),
            'abstract': self._extract_abstract(soup),
            'keywords': self._extract_keywords(soup),
            'full_text_sections': self._extract_full_text_sections(soup),
            'journal': self._extract_journal(soup),
            'issn': self._extract_issn(soup),
            'citation': self._extract_citation(soup),
            'received_date': self._extract_received_date(soup),
            'accepted_date': self._extract_accepted_date(soup),
            'published_date': self._extract_published_date(soup),
            'corresponding_author': self._extract_corresponding_author(soup),
            'affiliations': self._extract_affiliations(soup),
            'references': self._extract_references(soup),
        }
        return article_data
    
    def _extract_from_xml(self, soup: BeautifulSoup, url: str, pmcid: str) -> Dict:
        """Extract data from XML/PMC format."""
        article_data = {
            'url': url,
            'pmcid': f"PMC{pmcid}",
        }
        
        # Extract from XML structure - try multiple possible root elements
        article = (soup.find('article') or 
                  soup.find('pmc-articleset') or
                  soup.find('pmc-article') or
                  soup.find('article-meta'))
        
        # If we have pmc-articleset, get the article from it
        if not article and soup.find('pmc-articleset'):
            article = soup.find('pmc-articleset').find('article')
        
        # If we have front, get article-meta from it
        if not article:
            front = soup.find('front')
            if front:
                article = front.find('article-meta') or front
        
        if article:
            # Title
            title_elem = article.find('article-title') or article.find('title')
            if title_elem:
                article_data['title'] = ' '.join(title_elem.stripped_strings)
            
            # DOI
            article_id_doi = article.find('article-id', {'pub-id-type': 'doi'})
            if article_id_doi:
                article_data['doi'] = article_id_doi.get_text().strip()
            
            # Authors
            contrib_group = article.find('contrib-group')
            if contrib_group:
                authors = []
                for contrib in contrib_group.find_all('contrib', {'contrib-type': 'author'}):
                    name_elem = contrib.find('name')
                    if name_elem:
                        given = contrib.find('given-names')
                        surname = contrib.find('surname')
                        if given and surname:
                            authors.append(f"{given.get_text().strip()} {surname.get_text().strip()}")
                    else:
                        # Try alternative structure
                        given = contrib.find('given-names')
                        surname = contrib.find('surname')
                        if given and surname:
                            authors.append(f"{given.get_text().strip()} {surname.get_text().strip()}")
                if authors:
                    article_data['authors'] = ', '.join(authors)
            
            # Try alternative author extraction if contrib-group didn't work
            if 'authors' not in article_data or not article_data['authors']:
                authors = []
                for author in article.find_all('author'):
                    given = author.find('given-names')
                    surname = author.find('surname')
                    if given and surname:
                        authors.append(f"{given.get_text().strip()} {surname.get_text().strip()}")
                if authors:
                    article_data['authors'] = ', '.join(authors)
            
            # Abstract
            abstract = article.find('abstract')
            if abstract:
                abstract_paras = abstract.find_all('p')
                if abstract_paras:
                    article_data['abstract'] = '\n'.join([p.get_text().strip() for p in abstract_paras])
                else:
                    article_data['abstract'] = abstract.get_text().strip()
            
            # Keywords
            kwd_group = article.find('kwd-group')
            if kwd_group:
                keywords = [kwd.get_text().strip() for kwd in kwd_group.find_all('kwd')]
                if keywords:
                    article_data['keywords'] = ', '.join(keywords)
            
            # Journal
            journal = article.find('journal-title')
            if journal:
                article_data['journal'] = journal.get_text().strip()
            
            # Volume
            volume = article.find('volume')
            if volume:
                article_data['volume'] = volume.get_text().strip()
            
            # Issue
            issue = article.find('issue')
            if issue:
                article_data['issue'] = issue.get_text().strip()
            
            # ISSN (prefer epub then any)
            issn_elem = article.find('issn', {'pub-type': 'epub'}) or article.find('issn')
            if issn_elem and issn_elem.get_text():
                article_data['issn'] = issn_elem.get_text().strip()
            
            # Publication date and Year
            pub_date = article.find('pub-date')
            if pub_date:
                year_elem = pub_date.find('year')
                month = pub_date.find('month')
                day = pub_date.find('day')
                date_parts = []
                year_value = None
                if year_elem:
                    year_value = year_elem.get_text().strip()
                    date_parts.append(year_value)
                if month:
                    date_parts.append(month.get_text().strip())
                if day:
                    date_parts.append(day.get_text().strip())
                if date_parts:
                    article_data['publication_date'] = ' '.join(date_parts)
                if year_value:
                    article_data['year'] = year_value
            
            # PMID
            article_id_pmid = article.find('article-id', {'pub-id-type': 'pmid'})
            if article_id_pmid:
                article_data['pmid'] = article_id_pmid.get_text().strip()
            
            # Full text sections
            body = article.find('body')
            if body:
                sections = {}
                for sec in body.find_all('sec'):
                    title_elem = sec.find('title')
                    if title_elem:
                        title = title_elem.get_text().strip()
                        paras = sec.find_all('p')
                        content = '\n'.join([p.get_text().strip() for p in paras])
                        if title and content:
                            sections[title] = content
                article_data['full_text_sections'] = sections
            
            # Type
            article_data['type'] = 'article'
        
        return article_data

    # ----------------------------
    # Selenium-based helpers
    # ----------------------------

    def _get_selenium_driver(self):
        """
        Create a headless Firefox driver using webdriver-manager.
        Returns None if Selenium is not available.
        """
        if not _SELENIUM_AVAILABLE:
            return None

        options = FirefoxOptions()
        options.add_argument("--headless")
        options.set_preference("dom.webnotifications.enabled", False)
        options.set_preference("media.volume_scale", "0.0")

        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        driver.set_page_load_timeout(60)
        return driver

    def _update_session_from_selenium(self, driver) -> None:
        """
        Copy cookies from Selenium browser into requests session so that
        subsequent HTTP calls use the same authenticated context.
        """
        try:
            selenium_cookies = driver.get_cookies()
            for c in selenium_cookies:
                # Some cookies may miss domain/path; requests will still accept them
                self.session.cookies.set(
                    c.get("name"),
                    c.get("value"),
                    domain=c.get("domain"),
                    path=c.get("path") or "/",
                )
        except Exception:
            # Best-effort; ignore if anything goes wrong
            pass

    def _scrape_with_selenium(self, url: str, pmcid: str) -> Dict:
        """
        Use a real Firefox browser (headless via Selenium) to load the page,
        then parse the HTML with BeautifulSoup and reuse HTML extractors.

        This is useful when direct HTTP requests are blocked with 403.
        Reuses existing driver if available.
        """
        # Reuse existing driver if available
        if self._selenium_driver is None:
            driver = self._get_selenium_driver()
            if driver is None:
                raise RuntimeError("Selenium driver is not available")
            self._selenium_driver = driver
        else:
            driver = self._selenium_driver

        try:
            driver.get(url)

            # Optional: wait a short time for dynamic content (PMC pages are mostly static)
            driver.implicitly_wait(5)

            # Get final HTML after any redirects / JS
            page_source = driver.page_source

            # Update requests session with browser cookies for later HTTP calls
            self._update_session_from_selenium(driver)
            
            # Save cookies and headers to cache after getting them from Selenium
            self._save_session_cache()

            soup = BeautifulSoup(page_source, "lxml")
            result = self._extract_from_html(soup, url, pmcid)

            # If we at least have a title, consider it a success
            if result.get("title"):
                return result

            return result
        except Exception as e:
            # If driver failed, reset it
            if self._selenium_driver:
                try:
                    self._selenium_driver.quit()
                except:
                    pass
                self._selenium_driver = None
            raise
    
    def _extract_meta_tag(self, soup: BeautifulSoup, meta_names: List[str], 
                          multiple: bool = False, additional_attrs: Dict = None,
                          fallback_func: callable = None) -> Optional[str]:
        """
        General function to extract data from meta tags.
        
        Args:
            soup: BeautifulSoup object
            meta_names: List of meta tag name attributes to try (e.g., ['citation_doi', 'DC.Identifier'])
            multiple: If True, returns comma-separated string of all matching values
            additional_attrs: Additional attributes to match (e.g., {'scheme': 'doi'})
            fallback_func: Optional function to call if meta tags don't work
        
        Returns:
            String value(s) or None
        """
        if additional_attrs is None:
            additional_attrs = {}
        
        values = []
        
        for meta_name in meta_names:
            attrs = {'name': meta_name}
            attrs.update(additional_attrs)
            
            if multiple:
                # Find all matching meta tags
                meta_tags = soup.find_all('meta', attrs)
                for meta in meta_tags:
                    content = meta.get('content', '').strip()
                    if content:
                        values.append(content)
            else:
                # Find first matching meta tag
                meta_tag = soup.find('meta', attrs)
                if meta_tag:
                    content = meta_tag.get('content', '').strip()
                    if content:
                        return content
        
        if values:
            if multiple:
                return ', '.join(values)
            else:
                return values[0] if values else None
        
        # Try fallback function if provided
        if fallback_func:
            return fallback_func(soup)
        
        return None
    
    def _extract_doi(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract DOI from meta tags or content."""
        # Try meta tags first
        result = self._extract_meta_tag(
            soup, 
            meta_names=['citation_doi', 'DC.Identifier'],
            additional_attrs={'scheme': 'doi'} if soup.find('meta', {'name': 'DC.Identifier', 'scheme': 'doi'}) else {}
        )
        if result:
            return result
        
        # Try DC.Identifier without scheme constraint
        result = self._extract_meta_tag(soup, meta_names=['DC.Identifier'])
        if result:
            return result
        
        # Fallback: Try finding in text
        doi_pattern = r'10\.\d{4,}/[^\s]+'
        text = soup.get_text()
        match = re.search(doi_pattern, text)
        if match:
            return match.group(0)
        
        return None
    
    def _extract_publication_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract publication date."""
        return self._extract_meta_tag(
            soup, 
            meta_names=['citation_publication_date', 'DC.Date']
        )
    
    def _extract_year(self, soup: BeautifulSoup, publication_date: Optional[str] = None) -> Optional[str]:
        """Extract year from publication date or meta tags."""
        # First try to extract from publication_date if provided
        if publication_date:
            # Try to extract year from date string (e.g., "2013 Nov 5" or "2013")
            year_match = re.search(r'\b(19|20)\d{2}\b', publication_date)
            if year_match:
                return year_match.group(0)
        
        # Try meta tags
        year = self._extract_meta_tag(
            soup,
            meta_names=['citation_year', 'citation_publication_date']
        )
        if year:
            # Extract year from date string if needed
            year_match = re.search(r'\b(19|20)\d{2}\b', year)
            if year_match:
                return year_match.group(0)
            # If it's already just a year, return it
            if year.isdigit() and len(year) == 4:
                return year
        
        return None
    
    def _extract_volume(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract volume number."""
        def fallback(soup):
            volume_elem = soup.find('span', class_='volume')
            if volume_elem:
                return volume_elem.get_text().strip()
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_volume'],
            fallback_func=fallback
        )
    
    def _extract_issue(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract issue number."""
        def fallback(soup):
            issue_elem = soup.find('span', class_='issue')
            if issue_elem:
                return issue_elem.get_text().strip()
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_issue'],
            fallback_func=fallback
        )
    
    def _extract_type(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article type."""
        result = self._extract_meta_tag(soup, meta_names=['citation_article_type'])
        return result if result else 'article'
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article title."""
        def fallback(soup):
            # Try h1 tag
            title_h1 = soup.find('h1', class_='content-title')
            if title_h1:
                return title_h1.get_text().strip()
            
            # Try alternative h1
            title_h1 = soup.find('h1')
            if title_h1:
                return title_h1.get_text().strip()
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_title'],
            fallback_func=fallback
        )
    
    def _extract_authors(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract authors as a string."""
        def fallback(soup):
            # Try finding in content
            author_elem = soup.find('div', class_='contrib-group')
            if author_elem:
                author_names = author_elem.find_all('a', class_='nlm-person-name')
                if author_names:
                    authors = [name.get_text().strip() for name in author_names]
                    return ', '.join(authors)
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_author'],
            multiple=True,
            fallback_func=fallback
        )
    
    def _extract_pmcid(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        """Extract PMCID from URL or content."""
        # Extract from URL first
        pmcid_match = re.search(r'PMC(\d+)', url)
        if pmcid_match:
            return f"PMC{pmcid_match.group(1)}"
        
        # Try meta tag
        return self._extract_meta_tag(soup, meta_names=['citation_pmcid'])
    
    def _extract_pmid(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract PMID."""
        def fallback(soup):
            # Try finding in text
            pmid_pattern = r'PMID:\s*(\d+)'
            text = soup.get_text()
            match = re.search(pmid_pattern, text)
            if match:
                return match.group(1)
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_pmid'],
            fallback_func=fallback
        )
    
    def _extract_abstract(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract abstract text."""
        def fallback(soup):
            # Try multiple selectors
            abstract_selectors = [
                ('div', {'class': 'abstract'}),
                ('div', {'class': 'sec'}),
                ('div', {'id': 'abstract'}),
                ('section', {'class': 'abstract'}),
            ]
            
            for tag, attrs in abstract_selectors:
                abstract_elem = soup.find(tag, attrs)
                if abstract_elem:
                    # Get text but exclude headings
                    paragraphs = abstract_elem.find_all('p')
                    if paragraphs:
                        abstract_text = '\n'.join([p.get_text().strip() for p in paragraphs])
                        if abstract_text:
                            return abstract_text
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_abstract'],
            fallback_func=fallback
        )
    
    def _extract_keywords(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract keywords."""
        def fallback(soup):
            # Try finding in content
            kwd_group = soup.find('div', class_='kwd-group')
            if kwd_group:
                kwd_items = kwd_group.find_all('a', class_='kwd')
                if kwd_items:
                    keywords = [item.get_text().strip() for item in kwd_items]
                    return ', '.join(keywords)
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_keywords'],
            multiple=True,
            fallback_func=fallback
        )
    
    def _extract_full_text_sections(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract full text sections."""
        sections = {}
        
        # Find all section divs
        section_divs = soup.find_all('div', class_='sec')
        
        for section in section_divs:
            # Get section title
            title_elem = section.find('h2') or section.find('h3') or section.find('h4')
            if title_elem:
                title = title_elem.get_text().strip()
                
                # Get section content
                content_paragraphs = section.find_all('p')
                content = '\n'.join([p.get_text().strip() for p in content_paragraphs])
                
                if title and content:
                    sections[title] = content
        
        # Also try alternative structure
        if not sections:
            sec_elements = soup.find_all('section')
            for sec in sec_elements:
                title_elem = sec.find(['h2', 'h3', 'h4', 'h5'])
                if title_elem:
                    title = title_elem.get_text().strip()
                    content_paragraphs = sec.find_all('p')
                    content = '\n'.join([p.get_text().strip() for p in content_paragraphs])
                    if title and content:
                        sections[title] = content
        
        return sections
    
    def _extract_journal(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract journal name."""
        def fallback(soup):
            journal_elem = soup.find('div', class_='journal-title')
            if journal_elem:
                return journal_elem.get_text().strip()
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_journal_title'],
            fallback_func=fallback
        )
    
    def _extract_issn(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract ISSN from meta tags or page content."""
        def fallback(soup):
            # Try span/div that might contain ISSN (e.g. citation block)
            issn_elem = soup.find('span', class_='issn') or soup.find('div', class_='issn')
            if issn_elem and issn_elem.get_text():
                return issn_elem.get_text().strip()
            # Pattern: ISSN 1234-5678 or ISSN: 1234-5678
            issn_pattern = re.compile(r'ISSN[:\s]*([0-9]{4}-[0-9]{3}[0-9Xx])', re.I)
            text = soup.get_text()
            match = issn_pattern.search(text)
            if match:
                return match.group(1)
            return None
        
        return self._extract_meta_tag(
            soup,
            meta_names=['citation_issn', 'citation_issn_print', 'citation_issn_electronic'],
            fallback_func=fallback
        )
    
    def _extract_citation(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract full citation."""
        return self._extract_meta_tag(soup, meta_names=['citation_full_html'])
    
    def _extract_received_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract received date."""
        # Look for received date in history
        history = soup.find('div', class_='history-dates')
        if history:
            received = history.find(string=re.compile(r'Received', re.I))
            if received:
                # Try to find date near it
                parent = received.find_parent()
                if parent:
                    date_text = parent.get_text()
                    return date_text.strip()
        
        return None
    
    def _extract_accepted_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract accepted date."""
        history = soup.find('div', class_='history-dates')
        if history:
            accepted = history.find(string=re.compile(r'Accepted', re.I))
            if accepted:
                parent = accepted.find_parent()
                if parent:
                    date_text = parent.get_text()
                    return date_text.strip()
        
        return None
    
    def _extract_published_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract published date."""
        return self._extract_meta_tag(soup, meta_names=['citation_online_date'])
    
    def _extract_corresponding_author(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract corresponding author information."""
        corr_author = soup.find('div', class_='corresp')
        if corr_author:
            return corr_author.get_text().strip()
        
        return None
    
    def _extract_affiliations(self, soup: BeautifulSoup) -> List[str]:
        """Extract author affiliations."""
        affiliations = []
        affil_elements = soup.find_all('div', class_='aff')
        for affil in affil_elements:
            affil_text = affil.get_text().strip()
            if affil_text:
                affiliations.append(affil_text)
        
        return affiliations
    
    def _extract_references(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract references."""
        references = []
        ref_list = soup.find('div', class_='ref-list')
        if ref_list:
            ref_items = ref_list.find_all('div', class_='ref')
            for ref in ref_items:
                ref_text = ref.get_text().strip()
                if ref_text:
                    references.append({'text': ref_text})
        
        return references


    def batch_scrape(self, pmc_ids: List[int], output_dir: str = 'articles', 
                     delay: float = 0.5) -> Dict[str, Union[Article, Dict]]:
        """
        Scrape multiple PMC articles in batch.
        Optimized to reuse Selenium driver and cookies across requests.
        
        Args:
            pmc_ids: List of PMC IDs (without 'PMC' prefix, e.g., [4049904, 11089781])
            output_dir: Directory to save JSON files (default: 'articles')
            delay: Delay between requests in seconds (default: 0.5)
        
        Returns:
            Dictionary mapping PMCID to article data or error
        """
        import time
        
        results = {}
        total = len(pmc_ids)
        successful = 0
        failed = 0
        
        print(f"\n{'='*60}")
        print(f"Starting batch scraping of {total} articles")
        print(f"{'='*60}\n")
        
        # Test if cached cookies work by trying first article
        first_pmcid = f"PMC{pmc_ids[0]}"
        first_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{first_pmcid}/"
        print(f"Testing cached cookies with {first_pmcid}...", end=' ', flush=True)
        
        test_response = self.session.get(first_url, timeout=30, allow_redirects=True, verify=False)
        cookies_work = test_response.status_code == 200 or (test_response.status_code == 403 and len(test_response.content) > 1000)
        
        if not cookies_work and _SELENIUM_AVAILABLE:
            print("[FAILED] Refreshing cookies from Selenium...")
            if self._refresh_session_from_selenium():
                print("[SUCCESS] Cookies refreshed!")
            else:
                print("[WARNING] Could not refresh cookies, will try per-article")
        else:
            print("[OK] Cached cookies work!")
        
        print()
        
        for idx, pmcid_num in enumerate(pmc_ids, 1):
            pmcid = f"PMC{pmcid_num}"
            url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
            
            print(f"[{idx}/{total}] Scraping {pmcid}...", end=' ', flush=True)
            
            try:
                article_data = self.scrape_article(url)
                
                # Check if it's an error dict or Article instance
                if isinstance(article_data, dict) and 'error' in article_data:
                    print(f"[ERROR] {article_data.get('error', 'Unknown error')}")
                    failed += 1
                    results[pmcid] = article_data
                else:
                    # Success - article_data is Article instance
                    output_file = self.save_to_json(article_data, output_dir)
                    print(f"[SUCCESS] Saved to {output_file}")
                    successful += 1
                    results[pmcid] = article_data
                
            except Exception as e:
                print(f"[ERROR] Exception: {str(e)}")
                failed += 1
                results[pmcid] = {'error': str(e), 'url': url}
            
            # Delay between requests (except for the last one)
            if idx < total:
                time.sleep(delay)
        
        # Cleanup: close Selenium driver if it exists
        if self._selenium_driver:
            try:
                self._selenium_driver.quit()
                self._selenium_driver = None
            except:
                pass
        
        print(f"\n{'='*60}")
        print(f"Batch scraping completed!")
        print(f"  [SUCCESS] Successful: {successful}/{total}")
        print(f"  [FAILED] Failed: {failed}/{total}")
        print(f"  [OUTPUT] Directory: {output_dir}")
        print(f"{'='*60}\n")
        
        return results


def main():
    """Main function to test the scraper."""
    scraper = PMCScraper()
    
    # List of PMC IDs to scrape
    pmc_ids = [4049904, 11089781, 1351071, 1627071, 5767866, 6128885, 10031415, 9368379, 6109114, 12062735]
    
    # Batch scrape all articles
    results = scraper.batch_scrape(pmc_ids, output_dir='articles', delay=0.5)
    
    # Print summary
    print("\nSummary:")
    for pmcid, data in results.items():
        if isinstance(data, dict) and 'error' in data:
            print(f"  {pmcid}: [FAILED] {data.get('error', 'Unknown error')}")
        elif isinstance(data, Article):
            title = (data.Title or 'N/A')[:60] + '...' if len(data.Title or '') > 60 else (data.Title or 'N/A')
            print(f"  {pmcid}: [OK] {title}")
        else:
            title = data.get('title') or data.get('Title') or 'N/A'
            title = title[:60] + '...' if len(title) > 60 else title
            print(f"  {pmcid}: [OK] {title}")


if __name__ == '__main__':
    main()
