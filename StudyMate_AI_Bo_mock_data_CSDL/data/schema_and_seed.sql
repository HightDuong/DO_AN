-- StudyMate AI mock data v1.0
-- Run in an empty test database. PostgreSQL-compatible.
CREATE TABLE Lop (
  MaLop VARCHAR(4) PRIMARY KEY,
  TenLop VARCHAR(60) NOT NULL
);
CREATE TABLE MonHoc (
  MaMH VARCHAR(4) PRIMARY KEY,
  TenMH VARCHAR(60) NOT NULL,
  SoTinChi INTEGER NOT NULL CHECK (SoTinChi > 0)
);
CREATE TABLE SinhVien (
  MaSV VARCHAR(4) PRIMARY KEY,
  HoTen VARCHAR(40) NOT NULL,
  MaLop VARCHAR(4) NOT NULL,
  Email VARCHAR(80),
  FOREIGN KEY (MaLop) REFERENCES Lop(MaLop)
    ON DELETE RESTRICT
);
CREATE TABLE KetQua (
  MaSV VARCHAR(4) NOT NULL,
  MaMH VARCHAR(4) NOT NULL,
  Diem NUMERIC(3,1) NOT NULL
    CHECK (Diem BETWEEN 0 AND 10),
  PRIMARY KEY (MaSV, MaMH),
  FOREIGN KEY (MaSV) REFERENCES SinhVien(MaSV)
    ON DELETE RESTRICT,
  FOREIGN KEY (MaMH) REFERENCES MonHoc(MaMH)
    ON DELETE RESTRICT
);

INSERT INTO Lop VALUES
('CTK1', 'Công nghệ thông tin 1'),
('CTK2', 'Công nghệ thông tin 2');
INSERT INTO MonHoc VALUES
('CSDL', 'Cơ sở dữ liệu', 3),
('SQL', 'Truy vấn SQL', 2),
('LT', 'Lập trình', 3);
INSERT INTO SinhVien VALUES
('SV01', 'An', 'CTK1', 'an@demo.edu'),
('SV02', 'Binh', 'CTK1', 'binh@demo.edu'),
('SV03', 'Chi', 'CTK2', 'chi@demo.edu'),
('SV04', 'Dung', 'CTK2', NULL),
('SV05', 'Ha', 'CTK1', 'ha@demo.edu');
INSERT INTO KetQua VALUES
('SV01', 'CSDL', 8.0), ('SV01', 'SQL', 9.0),
('SV02', 'CSDL', 6.0), ('SV02', 'SQL', 7.5),
('SV03', 'CSDL', 9.0), ('SV03', 'LT', 8.0),
('SV04', 'SQL', 5.0), ('SV04', 'LT', 6.5);
