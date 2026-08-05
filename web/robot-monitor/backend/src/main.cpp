#include "crow.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_set>

namespace {
std::mutex clients_mutex;
std::unordered_set<crow::websocket::connection*> clients;
std::atomic_bool keep_running{true};
std::atomic_int mission_mode{0};  // 0=idle, 1=patrolling, 2=paused

std::string mission_state() {
  switch (mission_mode.load()) {
    case 1: return "巡检中";
    case 2: return "已暂停";
    default: return "待命";
  }
}

void broadcast(std::string message) {
  std::lock_guard<std::mutex> lock(clients_mutex);
  for (auto* client : clients) client->send_text(message);
}

void simulator_loop() {
  using namespace std::chrono_literals;
  double temperature = 25.6;
  double humidity = 58.0;
  double co = 12.0;
  double noise = 46.0;
  double x = 0.0;

  while (keep_running.load()) {
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    const auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
    const double t = timestamp / 1000.0;
    temperature = 25.6 + std::sin(t / 12.0) * 1.2;
    humidity = 58.0 + std::sin(t / 16.0) * 3.0;
    co = 12.0 + std::sin(t / 8.0) * 2.5;
    noise = 46.0 + std::sin(t / 4.0) * 4.0;
    if (mission_mode.load() == 1) x += 0.12;

    crow::json::wvalue message;
    message["type"] = "robot_status";
    message["timestamp"] = timestamp;
    message["online"] = true;
    message["mission_state"] = mission_state();
    message["temperature"] = std::round(temperature * 10.0) / 10.0;
    message["humidity"] = std::round(humidity * 10.0) / 10.0;
    message["co"] = std::round(co * 10.0) / 10.0;
    message["noise"] = std::round(noise * 10.0) / 10.0;
    message["x"] = std::round(x * 100.0) / 100.0;
    message["y"] = std::round(std::sin(x / 2.0) * 120.0) / 100.0;
    broadcast(message.dump());
    std::this_thread::sleep_for(1s);
  }
}

void handle_command(crow::websocket::connection& connection, const std::string& payload) {
  const auto request = crow::json::load(payload);
  crow::json::wvalue result;
  result["type"] = "command_result";
  result["ok"] = false;

  if (!request || !request.has("type") || request["type"].s() != "command" || !request.has("command")) {
    result["message"] = "命令格式错误";
    connection.send_text(result.dump());
    return;
  }

  const std::string command = request["command"].s();
  if (command == "start_patrol") {
    mission_mode.store(1);
    result["ok"] = true;
    result["message"] = "模拟后端已接收：开始巡检（未驱动真实电机）";
  } else if (command == "pause_patrol") {
    mission_mode.store(2);
    result["ok"] = true;
    result["message"] = "模拟后端已接收：暂停巡检";
  } else if (command == "stop_patrol") {
    mission_mode.store(0);
    result["ok"] = true;
    result["message"] = "模拟后端已接收：停止巡检";
  } else {
    result["message"] = "不支持的命令";
  }
  result["mission_state"] = mission_state();
  connection.send_text(result.dump());
}
}  // namespace

int main() {
  crow::SimpleApp app;

  CROW_ROUTE(app, "/api/health")([] {
    crow::json::wvalue body;
    body["ok"] = true;
    body["service"] = "robot-mock-backend";
    body["safe_mode"] = true;
    return crow::response{body};
  });

  CROW_WEBSOCKET_ROUTE(app, "/ws")
    .onopen([](crow::websocket::connection& connection) {
      std::lock_guard<std::mutex> lock(clients_mutex);
      clients.insert(&connection);
    })
    .onclose([](crow::websocket::connection& connection, const std::string&) {
      std::lock_guard<std::mutex> lock(clients_mutex);
      clients.erase(&connection);
    })
    .onmessage([](crow::websocket::connection& connection, const std::string& data, bool is_binary) {
      if (!is_binary) handle_command(connection, data);
    });

  std::signal(SIGINT, [](int) { keep_running.store(false); });
  std::thread simulator(simulator_loop);
  app.port(8080).multithreaded().run();
  keep_running.store(false);
  simulator.join();
}
