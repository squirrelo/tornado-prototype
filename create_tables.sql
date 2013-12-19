-- These tables are still prototype. The job_datatype and job_qiime
--- TABLES FOR POSTGRES

CREATE DATABASE qiita;

USE qiita;

CREATE TABLE qiita_users (
    qiita_username varchar(255) PRIMARY KEY,
    qiita_password varchar(255) NOT NULL,
    CONSTRAINT qiita_password_check CHECK (qiita_password <> '')
);

CREATE TABLE qiita_analysis (
    analysis_id bigserial PRIMARY KEY,
    qiita_username varchar(255) REFERENCES qiita_users(qiita_username),
    analysis_name text NOT NULL,
    analysis_studies text[] NOT NULL,
    analysis_metadata text[] NOT NULL,
    analysis_timestamp timestamp NOT NULL,
    analysis_done bool DEFAULT false
);

CREATE TABLE qiita_job (
    job_id bigserial PRIMARY KEY,
    analysis_id bigint REFERENCES qiita_analysis(analysis_id),
    job_datatype text NOT NULL,
    job_type text NOT NULL,
    job_options json NOT NULL,
    job_results text[],
    job_done bool DEFAULT false,
    job_error bool DEFAULT false
);


INSERT INTO qiita_users (qiita_username, qiita_password) VALUES ('admin', 'c7ad44cbad762a5da0a452f9e854fdc1e0e7a52a38015f23f3eab1d80b931dd472634dfac71cd34ebc35d16ab7fb8a90c81f975113d6c7538dc69dd8de9077ec');