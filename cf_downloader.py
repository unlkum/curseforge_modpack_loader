#!/usr/bin/env python3
import os
import sys
import re
import json
import zipfile
import shutil
import ssl
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Используем официальный ключ доступа API CurseForge, используемый в Prism Launcher
API_KEY = "$2a$10$bL4bIL5pUWqfcO7KQtnMReakwtfHbNKh6v1uTpKlzhwoueEJQnPnm"
BASE_URL = "https://api.curseforge.com/v1"

# Отключаем проверку SSL на случай устаревших корневых сертификатов в системе
ssl_context = ssl._create_unverified_context()

def get_headers():
    return {
        "x-api-key": API_KEY,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

def request_json(url, data=None):
    req = urllib.request.Request(url, headers=get_headers())
    if data is not None:
        req.add_header("Content-Type", "application/json")
        json_data = json.dumps(data).encode("utf-8")
        req.data = json_data
    
    with urllib.request.urlopen(req, context=ssl_context) as response:
        return json.loads(response.read().decode("utf-8"))

def download_file(url, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    req = urllib.request.Request(url, headers=get_headers())
    with urllib.request.urlopen(req, context=ssl_context) as response, open(filepath, "wb") as out_file:
        shutil.copyfileobj(response, out_file)

def get_modpack_by_slug(slug):
    print(f"[⚙️] Поиск сборки по slug: '{slug}'...")
    url = f"{BASE_URL}/mods/search?gameId=432&classId=4471&slug={slug}"
    result = request_json(url)
    if not result.get("data"):
        raise ValueError(f"Сборка '{slug}' не найдена в CurseForge.")
    return result["data"][0]

def get_modpack_files(mod_id):
    url = f"{BASE_URL}/mods/{mod_id}/files"
    result = request_json(url)
    return result.get("data", [])

def get_file_by_id(mod_id, file_id):
    url = f"{BASE_URL}/mods/{mod_id}/files/{file_id}"
    result = request_json(url)
    return result.get("data")

def merge_folders(src, dst):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            os.makedirs(d, exist_ok=True)
            merge_folders(s, d)
        else:
            shutil.copy2(s, d)

def process_modpack_zip(zip_path, output_dir):
    print(f"[📦] Чтение архива сборки: {zip_path}")
    temp_extract = os.path.join(output_dir, ".temp_extract")
    os.makedirs(temp_extract, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_extract)
        
    manifest_path = os.path.join(temp_extract, "manifest.json")
    if not os.path.exists(manifest_path):
        raise ValueError("Некорректный архив сборки! manifest.json отсутствует внутри.")
        
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
        
    name = manifest.get("name", "Unknown Modpack")
    version = manifest.get("version", "")
    mc_version = manifest.get("minecraft", {}).get("version", "Unknown")
    modloader_info = manifest.get("minecraft", {}).get("modLoaders", [{}])[0]
    modloader = modloader_info.get("id", "Unknown")
    
    print(f"\n==========================================")
    print(f" Название: {name} v{version}")
    print(f" Версия Minecraft: {mc_version}")
    print(f" Загрузчик модов: {modloader}")
    print(f"==========================================\n")
    
    files_to_download = manifest.get("files", [])
    print(f"[⚙️] Найдено модов для скачивания: {len(files_to_download)}")
    
    file_ids = [f["fileID"] for f in files_to_download]
    
    # Получаем информацию о файлах порциями по 100 штук
    chunk_size = 100
    file_details = []
    for i in range(0, len(file_ids), chunk_size):
        chunk = file_ids[i:i+chunk_size]
        print(f"[⚙️] Запрос информации о модах... ({min(i + chunk_size, len(file_ids))}/{len(file_ids)})")
        chunk_details = request_json(f"{BASE_URL}/mods/files", data={"fileIds": chunk})
        file_details.extend(chunk_details.get("data", []))
        
    details_map = {f["id"]: f for f in file_details}
    mods_dir = os.path.join(output_dir, "mods")
    os.makedirs(mods_dir, exist_ok=True)
    
    download_tasks = []
    for f in files_to_download:
        fid = f["fileID"]
        if fid in details_map:
            info = details_map[fid]
            file_name = info["fileName"]
            dl_url = info.get("downloadUrl")
            
            # Если прямая ссылка в API отсутствует (заблокирована автором для сторонних приложений)
            # конструируем прямой путь к файлу на CDN CurseForge самостоятельно
            if not dl_url:
                part1 = fid // 1000
                part2 = fid % 1000
                quoted_name = urllib.parse.quote(file_name)
                dl_url = f"https://edge.forgecdn.net/files/{part1}/{part2}/{quoted_name}"
            
            dest_path = os.path.join(mods_dir, file_name)
            download_tasks.append((dl_url, dest_path, file_name))
        else:
            print(f"[⚠️] Не удалось найти информацию о файле ID: {fid}")
            
    print(f"\n[🚀] Начинаем многопоточное скачивание {len(download_tasks)} файлов...")
    success_count = 0
    fail_count = 0
    
    # Скачиваем в 8 потоков для максимальной скорости
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_mod = {executor.submit(download_file, url, path): name for url, path, name in download_tasks}
        for future in as_completed(future_to_mod):
            mod_name = future_to_mod[future]
            try:
                future.result()
                success_count += 1
                print(f"[+] Скачан: {mod_name} ({success_count}/{len(download_tasks)})")
            except Exception as exc:
                print(f"[-] Ошибка загрузки {mod_name}: {exc}")
                fail_count += 1
                
    print(f"\n[🏁] Загрузка завершена! Успешно: {success_count}, Ошибок: {fail_count}")
    
    overrides_folder_name = manifest.get("overrides", "overrides")
    overrides_path = os.path.join(temp_extract, overrides_folder_name)
    if os.path.exists(overrides_path):
        print("[📂] Копирование конфигурационных файлов (overrides)...")
        merge_folders(overrides_path, output_dir)
                
    shutil.rmtree(temp_extract)
    print(f"\n[🎉] Сборка успешно собрана в директории: {os.path.abspath(output_dir)}")
    print(f"Для запуска используйте версию ядра: {modloader} (Minecraft {mc_version})")

def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python cf_downloader.py <URL сборки ИЛИ путь к скачанному ZIP> [ПАПКА_НАЗНАЧЕНИЯ]")
        print("\nПримеры:")
        print("  python cf_downloader.py https://www.curseforge.com/minecraft/modpacks/beyond-depth ./BeyondDepth")
        print("  python cf_downloader.py ./BeyondDepth-Ver12.7.0.zip ./BeyondDepth")
        sys.exit(1)
        
    input_source = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./modpack_output"
    
    # Сценарий 1: Указан локальный zip-файл
    if os.path.isfile(input_source) and input_source.lower().endswith(".zip"):
        try:
            process_modpack_zip(input_source, output_dir)
        except Exception as e:
            print(f"[❌] Ошибка при обработке архива: {e}")
            sys.exit(1)
        return
        
    # Сценарий 2: Указан URL-адрес
    if input_source.startswith("http://") or input_source.startswith("https://"):
        slug = None
        file_id = None
        
        # Парсим slug из ссылки
        slug_match = re.search(r'curseforge\.com/minecraft/modpacks/([^/?#\s]+)', input_source)
        if slug_match:
            slug = slug_match.group(1)
        else:
            parsed = urllib.parse.urlparse(input_source)
            parts = [p for p in parsed.path.split('/') if p]
            if "modpacks" in parts:
                idx = parts.index("modpacks")
                if idx + 1 < len(parts):
                    slug = parts[idx+1]
                    
        if not slug:
            print("[❌] Не удалось извлечь название (slug) сборки из ссылки.")
            sys.exit(1)
            
        file_match = re.search(r'/files/(\d+)', input_source)
        if file_match:
            file_id = int(file_match.group(1))
            
        try:
            modpack = get_modpack_by_slug(slug)
            modpack_id = modpack["id"]
            modpack_name = modpack["name"]
            print(f"[⚙️] Найдена сборка: {modpack_name} (ID: {modpack_id})")
            
            selected_file = None
            if file_id:
                print(f"[⚙️] Запрос конкретного файла ID: {file_id}...")
                selected_file = get_file_by_id(modpack_id, file_id)
            else:
                print("[⚙️] Получение списка версий сборки...")
                files = get_modpack_files(modpack_id)
                files.sort(key=lambda x: x["id"], reverse=True)
                
                # Ищем последнюю стабильную версию (Release = 1)
                releases = [f for f in files if f.get("releaseType") == 1]
                if releases:
                    selected_file = releases[0]
                elif files:
                    selected_file = files[0]
                    
            if not selected_file:
                print("[❌] Не найдено подходящих файлов для этой сборки.")
                sys.exit(1)
                
            file_id = selected_file["id"]
            file_name = selected_file["fileName"]
            print(f"[⚙️] Выбрана версия: {file_name} (ID: {file_id})")
            
            dl_url = selected_file.get("downloadUrl")
            if not dl_url:
                part1 = file_id // 1000
                part2 = file_id % 1000
                quoted_name = urllib.parse.quote(file_name)
                dl_url = f"https://edge.forgecdn.net/files/{part1}/{part2}/{quoted_name}"
                
            os.makedirs(output_dir, exist_ok=True)
            temp_zip_path = os.path.join(output_dir, "_temp_modpack.zip")
            print(f"[⚙️] Скачивание базового zip-архива сборки...")
            download_file(dl_url, temp_zip_path)
            
            process_modpack_zip(temp_zip_path, output_dir)
            
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
                
        except Exception as e:
            print(f"[❌] Произошла ошибка: {e}")
            sys.exit(1)
    else:
        print("[❌] Укажите корректный путь к .zip-файлу или ссылку на CurseForge.")
        sys.exit(1)

if __name__ == "__main__":
    main()