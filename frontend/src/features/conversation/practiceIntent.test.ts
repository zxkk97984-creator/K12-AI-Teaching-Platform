import { describe, expect, it } from "vitest";
import { practiceIntent } from "./practiceIntent";

describe("explicit practice requests", () => {
  it.each([["给本章出 10 道题",10],["请围绕数据分类生成二十道题",20],["生成 1.5 道题",1.5],["给我出21题",21],["生成-5道题",-5],["生成零道题",0],["生成1e3道题",1000]])("reads counts without truncating: %s", (text,count) => expect(practiceIntent(text)?.count).toBe(count));
  it.each(["别给我出题","不要生成练习","如何生成题目？","老师说“生成10题”是什么意思？","请解释这个知识点","我不需要你生成题目","请介绍AI生成题目的原理","请解释如何让AI出题"])("does not submit %s", text => expect(practiceIntent(text)).toBeNull());
  it.each(["给我出一百二十道题","生成1/2道题"])("rejects ambiguous or fractional counts: %s", text => expect(practiceIntent(text)?.count).toBeNaN());
  it("offers selection when no count is specified", () => expect(practiceIntent("给本章出几道题")?.count).toBeNull());
});
