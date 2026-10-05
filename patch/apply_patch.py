import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else pathlib.Path.home() / "RangeReduce"
here = pathlib.Path(__file__).resolve().parent

shutil.copy(here / "range_heat_tracker.h", root / "lib/rocksdb/db/range_heat_tracker.h")

it = root / "lib/rocksdb/db/arena_wrapped_db_iter.cc"
src = it.read_text()
if "range_heat_tracker.h" not in src:
    src = src.replace('#include "db/arena_wrapped_db_iter.h"\n',
                      '#include "db/arena_wrapped_db_iter.h"\n\n#include "db/range_heat_tracker.h"\n', 1)
    old = """  if (!rqdc_enabled) {
    return Refresh();
  }

  read_options_.enable_range_query_compaction = rqdc_enabled;"""
    new = """  if (!rqdc_enabled) {
    return Refresh();
  }

  if (RangeHeatTracker::Enabled() &&
      !RangeHeatTracker::ForDB(db_impl_).RecordAndAdmit(start_key, end_key)) {
    read_options_.enable_range_query_compaction = false;
    read_options_.range_start_key.clear();
    read_options_.range_end_key.clear();
    db_impl_->read_options_ = read_options_;
    return Refresh();
  }

  read_options_.enable_range_query_compaction = rqdc_enabled;"""
    assert old in src, "Refresh() anchor not found"
    src = src.replace(old, new, 1)
    it.write_text(src)
    print("patched", it)

ut = root / "src/utils.cc"
uts = ut.read_text()
if "Entries:" not in uts:
    old = """    cfd_details << "Level: " << level.level << ", Files: " << level.files.size()
                << ", Size: " << level.size << " bytes" << std::endl;"""
    new = """    uint64_t level_entries = 0, level_deletions = 0;
    for (const auto &file : level.files) {
      level_entries += file.num_entries;
      level_deletions += file.num_deletions;
    }
    cfd_details << "Level: " << level.level << ", Files: " << level.files.size()
                << ", Size: " << level.size << " bytes"
                << ", Entries: " << level_entries
                << ", Deletions: " << level_deletions << std::endl;"""
    assert old in uts, "LogTreeState anchor not found"
    uts = uts.replace(old, new, 1)
    ut.write_text(uts)
    print("patched", ut)

cm = root / "CMakeLists.txt"
cms = cm.read_text()
if "working_version PRIVATE TIMER PROFILE" not in cms:
    cms = cms.replace("add_executable(working_version ${SOURCES})",
                      "add_executable(working_version ${SOURCES})\ntarget_compile_definitions(working_version PRIVATE TIMER PROFILE)", 1)
    cms = cms.replace("target_compile_options(working_version PRIVATE -O2)",
                      "target_compile_options(working_version PRIVATE -O2 -fno-rtti)", 1)
    cm.write_text(cms)
    print("patched", cm)
