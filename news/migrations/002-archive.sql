ALTER TABLE articles ADD COLUMN revision TEXT NOT NULL DEFAULT '';
UPDATE articles SET revision=lower(hex(randomblob(16)));
CREATE TABLE archive_state (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    version TEXT NOT NULL
);
INSERT INTO archive_state VALUES(1,lower(hex(randomblob(16))));
CREATE TRIGGER archive_insert AFTER INSERT ON articles BEGIN
    UPDATE articles SET revision=lower(hex(randomblob(16))) WHERE id=NEW.id;
    UPDATE archive_state SET version=lower(hex(randomblob(16))) WHERE singleton=1;
END;
CREATE TRIGGER archive_update AFTER UPDATE OF
    id,reporter_id,reporter_name,title,summary,body_markdown,sources_json,
    article_date,coverage_start,coverage_end,published_at,deleted_at ON articles BEGIN
    UPDATE articles SET revision=lower(hex(randomblob(16))) WHERE id=NEW.id;
    UPDATE archive_state SET version=lower(hex(randomblob(16))) WHERE singleton=1;
END;
CREATE TRIGGER archive_delete AFTER DELETE ON articles BEGIN
    UPDATE archive_state SET version=lower(hex(randomblob(16))) WHERE singleton=1;
END;
PRAGMA user_version = 2;
