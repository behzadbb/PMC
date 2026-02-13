"""Fetch and transform PMC XML from NCBI E-utilities.

This service calls the NCBI `efetch` endpoint, parses JATS-like XML using
`lxml`, and maps extracted values into the `Article` DTO.

Data flow:
1. Normalize incoming PMC identifier.
2. Request XML from NCBI E-utilities.
3. Extract identifiers, bibliographic metadata, abstract, keywords, and body
   sections through XPath queries.
4. Return a populated `Article` instance, or a failure `Article` with
   `source=-1` and an `error_message`.
"""

import requests
from lxml import etree
from typing import Optional, Union
from datetime import datetime
from DTO.Article import Article


def _parse_publication_date(year: Optional[str], month: Optional[str], day: Optional[str]) -> Optional[datetime]:
    """
    Build a ``datetime`` from XML date parts.

    Missing month/day values default to ``1``. Invalid or incomplete values
    return ``None`` instead of raising an exception.

    Args:
        year: Publication year. Required for successful conversion.
        month: Publication month, if available.
        day: Publication day, if available.

    Returns:
        Parsed publication date, or ``None`` when parsing is not possible.
    """
    if not year:
        return None
    
    try:
        year_int = int(year)
        month_int = int(month) if month else 1
        day_int = int(day) if day else 1
        return datetime(year_int, month_int, day_int)
    except (ValueError, TypeError):
        return None


class Api_XML:
    """
    Retrieve a single PMC article via API and convert it to an ``Article`` DTO.

    The class is focused on API XML ingestion (source code ``2``), not FTP
    archives. Extraction relies on direct XPath lookups for predictable
    metadata mapping and good parsing performance.
    """
    
    def get_article_from_xml(self, pmc_id: Union[int, str]) -> Article:
        """
        Fetch one article from NCBI E-utilities and map it to ``Article``.

        The method accepts both raw numeric IDs and ``PMC``-prefixed strings,
        normalizes the identifier, then calls:
        ``https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi``.

        On success:
            - Returns an ``Article`` with ``source=2`` (XML API path).
        On failure:
            - Returns an ``Article`` with ``source=-1`` and ``error_message``
              describing HTTP, XML, or runtime issues.

        Args:
            pmc_id: PMC identifier (e.g., ``6109114`` or ``"PMC6109114"``).

        Returns:
            ``Article`` populated from XML content or error metadata.
        """
        # Clean PMC ID and prepare URLs
        pmc_id_str = str(pmc_id).replace('PMC', '') if isinstance(pmc_id, str) else str(pmc_id)
        article_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id_str}/"
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmc_id_str}&rettype=xml"
        
        try:
            # Fetch XML
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                print(f"[ERROR] Status {response.status_code}")
                return Article(
                    url=article_url,
                    pmcid=int(pmc_id_str),
                    source=-1,
                    error_message=f"HTTP {response.status_code}: {response.text[:200] if response.text else 'No response body'}"
                )
            
            # Parse XML with lxml (faster than BeautifulSoup)
            root = etree.fromstring(response.content)
            
            # Use XPath for efficient extraction
            ns = {'nlm': 'http://www.ncbi.nlm.nih.gov/JATS1'}
            
            # Find article element (handle namespace)
            article = root.find('.//article')
            if article is None:
                article = root.find('.//{http://www.ncbi.nlm.nih.gov/JATS1}article')
            if article is None:
                print("[ERROR] Article element not found")
                return Article(
                    url=article_url,
                    pmcid=int(pmc_id_str),
                    source=-1,
                    error_message="Article element not found in XML"
                )
            
            # Build article data dictionary with direct XPath queries
            article_data = {
                'url': article_url,
                'pmcid': int(pmc_id_str),
                'source': 2,  # XML_API
                'type': 'article',
            }
            
            # Extract identifiers
            article_data['doi'] = self._get_text(article, './/article-id[@pub-id-type="doi"]')
            pmid_text = self._get_text(article, './/article-id[@pub-id-type="pmid"]')
            if pmid_text:
                try:
                    article_data['pmid'] = int(pmid_text)
                except ValueError:
                    article_data['pmid'] = pmid_text
            
            # Extract title
            article_data['title'] = self._get_text(article, './/article-title') or self._get_text(article, './/title')
            
            # Extract authors (more efficient single query)
            authors = []
            for contrib in article.xpath('.//contrib[@contrib-type="author"]'):
                given = self._get_text(contrib, './/given-names')
                surname = self._get_text(contrib, './/surname')
                if given and surname:
                    authors.append(f"{given} {surname}")
            if authors:
                article_data['authors'] = ', '.join(authors)
            
            # Extract abstract
            abstract = article.find('.//abstract')
            if abstract is not None:
                paras = abstract.findall('.//p')
                article_data['abstract'] = '\n'.join([p.text or '' for p in paras if p.text]) if paras else (abstract.text or '')
            
            # Extract keywords
            keywords = [k.text for k in article.findall('.//kwd') if k.text]
            if keywords:
                article_data['keywords'] = ', '.join(keywords)
            
            # Extract journal
            article_data['journal'] = self._get_text(article, './/journal-title')
            
            # Extract volume and issue (try to convert to int)
            vol_text = self._get_text(article, './/volume')
            if vol_text:
                try:
                    article_data['volume'] = int(vol_text)
                except ValueError:
                    article_data['volume'] = vol_text
            
            issue_text = self._get_text(article, './/issue')
            if issue_text:
                try:
                    article_data['issue'] = int(issue_text)
                except ValueError:
                    article_data['issue'] = issue_text
            
            # Extract publication date and year
            pub_date = article.find('.//pub-date[@pub-type="epub"]')
            if pub_date is None:
                pub_date = article.find('.//pub-date')
            if pub_date is not None:
                year = self._get_text(pub_date, './/year')
                month = self._get_text(pub_date, './/month')
                day = self._get_text(pub_date, './/day')
                
                # Parse to datetime
                article_data['publication_date'] = _parse_publication_date(year, month, day)
                
                if year:
                    article_data['year'] = year
            
            # Extract full text sections
            body = article.find('.//body')
            if body is not None:
                sections = {}
                for sec in body.findall('.//sec'):
                    title_elem = sec.find('.//title')
                    if title_elem is not None and title_elem.text:
                        title = title_elem.text.strip()
                        paras = sec.findall('.//p')
                        content = '\n'.join([p.text or '' for p in paras if p.text]).strip()
                        if title and content:
                            sections[title] = content
                if sections:
                    article_data['full_text_sections'] = sections
            
            # Convert to Article DTO
            return Article(**article_data)
            
        except requests.RequestException as e:
            print(f"[ERROR] Request failed: {str(e)}")
            pmc_id_str = str(pmc_id).replace('PMC', '') if isinstance(pmc_id, str) else str(pmc_id)
            article_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id_str}/"
            return Article(
                url=article_url,
                pmcid=int(pmc_id_str),
                source=-1,
                error_message=f"Request failed: {str(e)}"
            )
        except etree.XMLSyntaxError as e:
            print(f"[ERROR] XML parsing failed: {str(e)}")
            pmc_id_str = str(pmc_id).replace('PMC', '') if isinstance(pmc_id, str) else str(pmc_id)
            article_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id_str}/"
            return Article(
                url=article_url,
                pmcid=int(pmc_id_str),
                source=-1,
                error_message=f"XML parsing failed: {str(e)}"
            )
        except Exception as e:
            print(f"[ERROR] {str(e)}")
            pmc_id_str = str(pmc_id).replace('PMC', '') if isinstance(pmc_id, str) else str(pmc_id)
            article_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id_str}/"
            return Article(
                url=article_url,
                pmcid=int(pmc_id_str),
                source=-1,
                error_message=f"Unexpected error: {str(e)}"
            )
    
    def _get_text(self, element, xpath: str) -> Optional[str]:
        """
        Safely resolve a relative XPath and return stripped text.

        Args:
            element: Parent XML element to query from.
            xpath: Relative XPath expression to locate a child node.

        Returns:
            Node text with surrounding whitespace removed, or ``None`` if the
            node/text is missing.
        """
        if element is None:
            return None
        result = element.find(xpath)
        return result.text.strip() if result is not None and result.text else None