cmake_minimum_required(VERSION 3.0.2)
project(scale_planner_bridge)

find_package(catkin REQUIRED COMPONENTS
  costmap_2d geometry_msgs message_generation nav_core nav_msgs pluginlib roscpp tf2 tf2_ros)

add_service_files(FILES Initialize.srv Step.srv)
generate_messages(DEPENDENCIES geometry_msgs nav_msgs)

catkin_package(CATKIN_DEPENDS costmap_2d geometry_msgs message_runtime nav_core nav_msgs pluginlib roscpp tf2 tf2_ros)
include_directories(${catkin_INCLUDE_DIRS})

add_executable(planner_bridge_node src/planner_bridge_node.cpp)
add_dependencies(planner_bridge_node ${${PROJECT_NAME}_EXPORTED_TARGETS} ${catkin_EXPORTED_TARGETS})
target_link_libraries(planner_bridge_node ${catkin_LIBRARIES})

catkin_install_python(PROGRAMS scripts/dwa_e0_smoke.py DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(TARGETS planner_bridge_node RUNTIME DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(DIRECTORY config launch DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
