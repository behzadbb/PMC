"""Quick test for Ftp_XML ISSN extraction."""
from Services.Ftp_XML import Ftp_XML

# Minimal JATS-style XML with journal and ISSN (no default ns so .// finds elements)
XML_SAMPLE = b"""<?xml version="1.0"?>
<article>
  <front>
    <journal-meta>
      <journal-title>Test Journal</journal-title>
      <issn pub-type="epub">1234-5678</issn>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmc">PMC99999</article-id>
      <article-title>Test Article</article-title>
      <pub-date pub-type="epub"><year>2024</year><month>1</month><day>1</day></pub-date>
    </article-meta>
  </front>
  <body><sec><title>Intro</title><p>Text</p></sec></body>
</article>"""

def main():
    ftp = Ftp_XML()
    article = ftp.parse_xml_to_article(XML_SAMPLE, 99999)
    print("Journal:", article.Journal)
    print("ISSN:", article.ISSN)
    print("PMCID:", article.PMCID)
    assert article.ISSN == "1234-5678", "Expected ISSN 1234-5678"
    print("OK: ISSN extracted correctly")

if __name__ == "__main__":
    main()
