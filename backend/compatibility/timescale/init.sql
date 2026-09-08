\set ON_ERROR_STOP on

CREATE ROLE fixture_reader LOGIN PASSWORD 'fixture-only';
CREATE ROLE fixture_no_stats LOGIN PASSWORD 'fixture-only';
CREATE ROLE fixture_no_metadata LOGIN PASSWORD 'fixture-only';

CREATE DATABASE plain_fixture TEMPLATE template0;
CREATE DATABASE timescale_fixture TEMPLATE template0;
CREATE DATABASE lifecycle_fixture TEMPLATE template0;

\connect lifecycle_fixture
CREATE TABLE public.fixture_marker (ready integer NOT NULL CHECK (ready = 1));
INSERT INTO public.fixture_marker VALUES (1);

\connect plain_fixture
CREATE EXTENSION hstore;
CREATE TABLE public.ordinary (id integer PRIMARY KEY, value text NOT NULL);
INSERT INTO public.ordinary VALUES (1, 'first'), (2, 'second'), (3, 'third');
CREATE TABLE public.fixture_marker (ready integer NOT NULL CHECK (ready = 1));
INSERT INTO public.fixture_marker VALUES (1);

\connect timescale_fixture
CREATE EXTENSION timescaledb;
\i /fixtures/data.sql
\i /fixtures/storage.sql
\i /fixtures/permissions.sql
CREATE TABLE public.fixture_marker (ready integer NOT NULL CHECK (ready = 1));
INSERT INTO public.fixture_marker VALUES (1);
