"""
Parse PMC XML articles from FTP-distributed ``tar.gz`` archives.

This module focuses on archive-based ingestion (source code ``1``). It reads
XML files incrementally, transforms them into `Article` DTOs, and supports
streaming conversion to JSON without loading all records into memory.
"""

import io
import tarfile
import json
import os
import re
from pathlib import Path
from typing import List, Optional, Iterator

# Max articles to hold in memory before writing a batch file
BATCH_SIZE = 10_000
from datetime import datetime
from lxml import etree
from DTO.Article import Article


class Ftp_XML:
    """
    Transform FTP XML archive entries into ``Article`` DTO instances.

    Primary responsibilities:
    - Parse single XML payloads to structured DTOs.
    - Iterate over archive members with generator-based processing.
    - Persist DTO output to JSON in an incremental, low-memory workflow.
    """
    
    def __init__(self):
        """Initialize the FTP XML parser instance."""
        self.pmc_ids = []
    
    @staticmethod
    def _parse_publication_date(year: Optional[str], month: Optional[str], day: Optional[str]) -> Optional[datetime]:
        """
        Build a ``datetime`` from XML date components.

        Missing month/day values default to ``1``. Invalid values are handled
        gracefully by returning ``None``.

        Args:
            year: Publication year text (required).
            month: Publication month text.
            day: Publication day text.

        Returns:
            Parsed publication date, or ``None`` when parsing fails.
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
    
    @staticmethod
    def extract_pmc_id_from_filename(filename: str) -> Optional[int]:
        """
        Extract numeric PMC identifier from an archive member filename.

        Args:
            filename: Archive member path/name, such as ``PMC000123456.xml``.

        Returns:
            Integer PMC ID if the ``PMC<digits>`` pattern is found; otherwise
            ``None``.
        """
        match = re.search(r'PMC(\d+)', filename)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None
    
    def parse_xml_to_article(self, xml_content: bytes, pmc_id: int) -> Article:
        """
        Parse one XML document and map extracted fields into ``Article``.

        Extraction includes identifiers, bibliographic metadata, abstract,
        keywords, publication date, and body sections. If XML does not provide
        a valid PMC identifier, the method keeps the filename-derived fallback.

        Args:
            xml_content: Raw XML bytes from a ``tar.gz`` member.
            pmc_id: Fallback PMC ID inferred from filename.

        Returns:
            ``Article`` with ``source=1`` for FTP pipeline output. When parsing
            fails, returns an ``Article`` containing error metadata.
        """
        try:
            # Parse XML with lxml
            root = etree.fromstring(xml_content)
            
            # The root element is typically the article element
            article = root
            if article.tag != 'article':
                # Try to find article element if root is not article
                article = root.find('.//article')
                if article is None:
                    # Try with namespace
                    article = root.find('.//{http://www.ncbi.nlm.nih.gov/JATS1}article')
            
            if article is None:
                return Article(
                    url=f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id}/",
                    pmcid=pmc_id,
                    source=1,  # FTP
                    error_message="Article element not found in XML"
                )
            
            # Extract identifiers - try to get PMC ID from XML first
            pmc_id_elem = article.find('.//article-id[@pub-id-type="pmc"]')
            extracted_pmc_id = pmc_id
            if pmc_id_elem is not None and pmc_id_elem.text:
                # Extract PMC ID from XML (e.g., "PMC11000225" -> 11000225)
                pmc_id_text = pmc_id_elem.text.strip()
                if pmc_id_text.startswith('PMC'):
                    try:
                        extracted_pmc_id = int(pmc_id_text.replace('PMC', ''))
                    except ValueError:
                        # If conversion fails, use the one from filename
                        extracted_pmc_id = pmc_id
                else:
                    try:
                        extracted_pmc_id = int(pmc_id_text)
                    except ValueError:
                        # If conversion fails, use the one from filename
                        extracted_pmc_id = pmc_id
            # If PMC ID not found in XML, use the one from filename (already set)
            
            # Build article data dictionary
            article_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{extracted_pmc_id}/"
            article_data = {
                'url': article_url,
                'pmcid': extracted_pmc_id,
                'source': 1,  # FTP
                'type': 'article',
            }
            
            # Extract DOI
            doi_elem = article.find('.//article-id[@pub-id-type="doi"]')
            article_data['doi'] = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None
            
            # Extract PMID - set to None if not found
            pmid_elem = article.find('.//article-id[@pub-id-type="pmid"]')
            if pmid_elem is not None and pmid_elem.text:
                try:
                    article_data['pmid'] = int(pmid_elem.text.strip())
                except (ValueError, AttributeError):
                    article_data['pmid'] = None
            else:
                article_data['pmid'] = None
            
            # Extract title - use itertext() to get all text including nested elements
            title_elem = article.find('.//article-title')
            if title_elem is not None:
                title_text = ' '.join(title_elem.itertext()).strip()
                article_data['title'] = title_text if title_text else None
            else:
                # Fallback to title element
                title_elem = article.find('.//title')
                article_data['title'] = ' '.join(title_elem.itertext()).strip() if title_elem is not None else None
            
            # Extract authors
            authors = []
            for contrib in article.findall('.//contrib[@contrib-type="author"]'):
                surname_elem = contrib.find('.//surname')
                given_elem = contrib.find('.//given-names')
                if surname_elem is not None and given_elem is not None:
                    surname = surname_elem.text.strip() if surname_elem.text else ''
                    given = given_elem.text.strip() if given_elem.text else ''
                    if surname and given:
                        authors.append(f"{given} {surname}")
            if authors:
                article_data['authors'] = ', '.join(authors)
            
            # Extract abstract - handle both structured and unstructured abstracts
            abstract = article.find('.//abstract')
            if abstract is not None:
                # Try to get paragraphs first
                paras = abstract.findall('.//p')
                if paras:
                    abstract_text = '\n'.join([' '.join(p.itertext()).strip() for p in paras if p is not None])
                else:
                    # If no paragraphs, get all text from abstract
                    abstract_text = ' '.join(abstract.itertext()).strip()
                article_data['abstract'] = abstract_text if abstract_text else None
            else:
                article_data['abstract'] = None
            
            # Extract keywords
            keywords = []
            for kwd in article.findall('.//kwd'):
                if kwd.text:
                    keywords.append(kwd.text.strip())
            if keywords:
                article_data['keywords'] = ', '.join(keywords)
            
            # Extract journal
            journal_elem = article.find('.//journal-title')
            article_data['journal'] = journal_elem.text.strip() if journal_elem is not None and journal_elem.text else None
            
            # Extract volume and issue
            vol_elem = article.find('.//volume')
            if vol_elem is not None and vol_elem.text:
                vol_text = vol_elem.text.strip()
                try:
                    article_data['volume'] = int(vol_text)
                except ValueError:
                    article_data['volume'] = vol_text
            
            issue_elem = article.find('.//issue')
            if issue_elem is not None and issue_elem.text:
                issue_text = issue_elem.text.strip()
                try:
                    article_data['issue'] = int(issue_text)
                except ValueError:
                    article_data['issue'] = issue_text
            
            # Extract publication date and year
            # Priority order: epub > ppub > pmc-release > any other pub-date
            pub_date = None
            pub_date_types = ['epub', 'ppub', 'pmc-release']
            
            # Try to find pub-date in priority order
            for pub_type in pub_date_types:
                pub_date = article.find(f'.//pub-date[@pub-type="{pub_type}"]')
                if pub_date is not None:
                    break
            
            # If no priority pub-date found, try any pub-date
            if pub_date is None:
                pub_date = article.find('.//pub-date')
            
            if pub_date is not None:
                year_elem = pub_date.find('.//year')
                month_elem = pub_date.find('.//month')
                day_elem = pub_date.find('.//day')
                
                year = year_elem.text.strip() if year_elem is not None and year_elem.text else None
                month = month_elem.text.strip() if month_elem is not None and month_elem.text else None
                day = day_elem.text.strip() if day_elem is not None and day_elem.text else None
                
                # Parse to datetime
                article_data['publication_date'] = self._parse_publication_date(year, month, day)
                
                # Extract year separately
                if year:
                    article_data['year'] = year
            
            # Extract full text sections
            body = article.find('.//body')
            if body is not None:
                sections = {}
                for sec in body.findall('.//sec'):
                    title_elem = sec.find('.//title')
                    if title_elem is not None:
                        # Get title text using itertext to handle nested elements
                        title = ' '.join(title_elem.itertext()).strip()
                        if title:
                            # Get all paragraphs in this section
                            paras = sec.findall('.//p')
                            if paras:
                                content = '\n'.join([' '.join(p.itertext()).strip() for p in paras if p is not None])
                            else:
                                # If no paragraphs, get all text from section
                                content = ' '.join(sec.itertext()).strip()
                                # Remove title from content
                                if content.startswith(title):
                                    content = content[len(title):].strip()
                            
                            if content:
                                sections[title] = content
                if sections:
                    article_data['full_text_sections'] = sections
            
            # Convert to Article DTO
            article_obj = Article(**article_data)
            
            self.pmc_ids.append(pmc_id)
            
            # Clear XML tree from memory
            root.clear()
            del root
            del article
            
            return article_obj
            
        except Exception as e:
            return Article(
                url=f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id}/",
                pmcid=pmc_id,
                source=1,  # FTP
                error_message=f"XML parsing error: {str(e)}"
            )
    
    def process_tar_gz_file(self, tar_gz_file_path: str) -> Iterator[Article]:
        """
        Stream-parse a ``tar.gz`` archive and yield ``Article`` objects.

        This generator is designed for large archives: it reads one XML member,
        converts it, yields the DTO, and releases temporary objects before
        moving to the next member.

        Args:
            tar_gz_file_path: Path to the input ``tar.gz`` archive.

        Yields:
            Parsed ``Article`` instances for XML files only.

        Notes:
            - Non-XML members are skipped.
            - Per-file processing errors are logged and do not stop the stream.
        """
        if not os.path.exists(tar_gz_file_path):
            print(f"[ERROR] File not found: {tar_gz_file_path}")
            return
        
        with tarfile.open(tar_gz_file_path, 'r:gz') as tar:
            members = tar.getmembers()
            total_files = len([m for m in members if m.name.endswith('.xml')])
            print(f"[INFO] Found {total_files} XML files in archive")
            
            processed = 0
            flag_first_article = True
            
            for member in members:
                if not member.name.endswith('.xml'):
                    continue
                
                processed += 1
                if processed % 1000 == 0:
                    print(f"[PROGRESS] Processed {processed}/{total_files} files...")
                
                try:
                    # Extract XML content
                    xml_file = tar.extractfile(member)
                    if xml_file is None:
                        continue
                    
                    try:
                        xml_content = xml_file.read()
                        
                        if flag_first_article:
                            flag_first_article = False
                            # Show first 200 characters of XML content for debugging
                            xml_preview = xml_content[:200].decode('utf-8', errors='ignore') if isinstance(xml_content, bytes) else str(xml_content)[:200]
                            print(f"[INFO] First article XML preview (first 200 chars): {xml_preview}...")
                        
                        # Extract PMC ID from filename
                        pmc_id = self.extract_pmc_id_from_filename(member.name)
                        if pmc_id is None:
                            print(f"[WARNING] Could not extract PMC ID from {member.name}, skipping...")
                            continue
                        
                        # Parse XML to Article
                        article = self.parse_xml_to_article(xml_content, pmc_id)
                        
                        # Clear XML content from memory
                        del xml_content
                        
                        yield article
                        
                        # Clear article from memory after yielding
                        del article
                    finally:
                        # Close file handle
                        if xml_file:
                            xml_file.close()
                        
                except Exception as e:
                    print(f"[ERROR] Failed to process {member.name}: {str(e)}")
                    continue

    def _article_to_dict(self, article: Article) -> dict:
        """Serialize Article to dict for JSON (Pydantic v1/v2 compatible)."""
        try:
            return article.model_dump(mode='json', exclude_none=False)
        except (AttributeError, TypeError):
            try:
                return article.dict(exclude_none=False)
            except AttributeError:
                return article.model_dump(exclude_none=False)

    def _write_batch(self, articles: List[Article], file_path: Path) -> None:
        """
        Write a list of articles to a compressed .json.tar.gz file.
        The archive contains a single .json file (tar + gzip).
        """
        if not articles:
            return
        payload = [self._article_to_dict(a) for a in articles]
        json_bytes = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
        inner_name = file_path.name.replace('.tar.gz', '') if file_path.name.endswith('.tar.gz') else file_path.stem + '.json'
        info = tarfile.TarInfo(name=inner_name)
        info.size = len(json_bytes)
        with tarfile.open(file_path, 'w:gz') as tar:
            tar.addfile(info, io.BytesIO(json_bytes))

    def convert_tar_gz_to_json(self, tar_gz_file_path: str, output_json_path: str = None) -> int:
        """
        Convert an FTP ``tar.gz`` archive into batch JSON files and a PMC IDs list.

        Output directory is the archive path with ``.tar.gz`` removed. Creates
        batch_0000.json.tar.gz, batch_0001.json.tar.gz, ... and pmc_ids.txt.

        Args:
            tar_gz_file_path: Input archive path.
            output_json_path: Unused; kept for API compatibility.

        Returns:
            Number of successfully serialized articles.
        """
        print(f"[STEP 1] Loading tar.gz file: {tar_gz_file_path}")
        if not os.path.exists(tar_gz_file_path):
            print(f"[ERROR] File not found: {tar_gz_file_path}")
            return 0

        # Derive output directory: remove ".tar.gz" from archive filename
        input_path = Path(tar_gz_file_path)
        archive_name = input_path.name
        if archive_name.lower().endswith('.tar.gz'):
            base_name = archive_name[:-7]  # len('.tar.gz') == 7
        else:
            base_name = input_path.stem
        dir_path = input_path.parent / base_name
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[ERROR] Cannot create output directory {dir_path}: {e}")
            return 0

        print(f"[STEP 2] Extracting XML files from tar.gz (output dir: {dir_path})...")
        article_count = 0
        batch: List[Article] = []
        batch_index = 0
        files_written = 0
        pmc_ids_path = dir_path / "pmc_ids.txt"
        pmc_ids_list: List[int] = []

        try:
            for article in self.process_tar_gz_file(tar_gz_file_path):
                article_count += 1
                batch.append(article)
                if article.PMCID is not None:
                    pmc_ids_list.append(article.PMCID)

                if len(batch) > BATCH_SIZE:
                    batch_file = dir_path / f"batch_{batch_index:04d}.json.tar.gz"
                    self._write_batch(batch, batch_file)
                    print(f"[INFO] Wrote batch {batch_index} ({len(batch)} articles) -> {batch_file}")
                    files_written += 1
                    batch.clear()
                    batch_index += 1

            if batch:
                batch_file = dir_path / f"batch_{batch_index:04d}.json.tar.gz"
                self._write_batch(batch, batch_file)
                print(f"[INFO] Wrote final batch {batch_index} ({len(batch)} articles) -> {batch_file}")
                files_written += 1
                batch.clear()

            # Write all PMC IDs to file in one go
            if pmc_ids_list:
                with open(pmc_ids_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(str(pid) for pid in pmc_ids_list) + '\n')
            print(f"[INFO] Wrote PMC IDs to {pmc_ids_path}")
            print(f"\n[SUCCESS] Saved {article_count} articles to {dir_path} ({files_written} file(s))")
        except Exception as e:
            print(f"[ERROR] Failed to process tar.gz file: {str(e)}")
            return article_count

        return article_count
