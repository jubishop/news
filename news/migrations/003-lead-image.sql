ALTER TABLE articles ADD COLUMN lead_image_json TEXT
    CHECK(lead_image_json IS NULL OR json_valid(lead_image_json));
DROP TRIGGER archive_update;
CREATE TRIGGER archive_update AFTER UPDATE OF
    id,reporter_id,reporter_name,title,summary,body_markdown,sources_json,
    article_date,coverage_start,coverage_end,published_at,deleted_at,lead_image_json ON articles BEGIN
    UPDATE articles SET revision=lower(hex(randomblob(16))) WHERE id=NEW.id;
    UPDATE archive_state SET version=lower(hex(randomblob(16))) WHERE singleton=1;
END;
PRAGMA user_version = 3;
