"""Smoke test for API XML to `Article` DTO conversion.

The script exercises `Services.Api_XML.Api_XML` against a single PMC ID,
prints key extracted fields, and writes the DTO payload to ``articles/`` as
JSON. It is useful for quickly validating API access, XML parsing, and DTO
serialization compatibility (Pydantic v1/v2 fallback paths).
"""

from Services.Api_XML import Api_XML

def main():
    """Run one end-to-end XML API fetch and local serialization test."""
    api_xml = Api_XML()
    pmc_id = 6109114
    
    print("=" * 60)
    print("Testing Optimized XML API to Article DTO Conversion")
    print("=" * 60)
    print()
    
    article = api_xml.get_article_from_xml(pmc_id)
    
    if article:
        print("\n" + "=" * 60)
        print("Article DTO Created Successfully!")
        print("=" * 60)
        print(f"PMCID: {article.PMCID}")
        print(f"Title: {article.Title}")
        print(f"Year: {article.Year}")
        print(f"Authors: {article.Authors}")
        print(f"Journal: {article.Journal}")
        print(f"Source: {article.source}")
        print(f"Has Abstract: {bool(article.Abstract)}")
        print(f"Has Full Text Sections: {bool(article.Full_Text_Sections)}")
        print(f"Number of Sections: {len(article.Full_Text_Sections) if article.Full_Text_Sections else 0}")
        
        # Save to JSON
        try:
            import os
            os.makedirs("articles", exist_ok=True)
            output_file = f"articles/PMC{pmc_id}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                import json
                try:
                    # Use model_dump_json for Pydantic v2 which handles datetime serialization
                    article_json = article.model_dump_json(exclude_none=False)
                    f.write(article_json)
                except AttributeError:
                    # Fallback for Pydantic v1
                    article_dict = article.dict(exclude_none=False)
                    json.dump(article_dict, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n[SAVED] Article saved to {output_file}")
        except Exception as e:
            print(f"\n[ERROR] Failed to save: {str(e)}")
    else:
        print("\n[FAILED] Could not create Article DTO")


if __name__ == "__main__":
    main()
