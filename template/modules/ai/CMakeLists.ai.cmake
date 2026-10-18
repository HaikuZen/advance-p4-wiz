
# the AI module's model: ESP-DL wants it 16-byte aligned, so its own embed helper, not EMBED_FILES
idf_component_get_property(espdl_dir espressif__esp-dl COMPONENT_DIR)
set(cmake_dir ${espdl_dir}/fbs_loader/cmake)
include(${cmake_dir}/utilities.cmake)
target_add_aligned_binary_data(${COMPONENT_LIB} models/digit.espdl BINARY)
