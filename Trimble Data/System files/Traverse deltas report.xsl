<?xml version='1.0' encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" >

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="html" omit-xml-declaration="no"  encoding="utf-8"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="string('.')"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="string(',')"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN="?"
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="string('#0')"/>
<xsl:variable name="DecPl1" select="string(concat('#0', $DecPt, '0'))"/>
<xsl:variable name="DecPl2" select="string(concat('#0', $DecPt, '00'))"/>
<xsl:variable name="DecPl3" select="string(concat('#0', $DecPt, '000'))"/>
<xsl:variable name="DecPl4" select="string(concat('#0', $DecPt, '0000'))"/>
<xsl:variable name="DecPl5" select="string(concat('#0', $DecPt, '00000'))"/>
<xsl:variable name="DecPl6" select="string(concat('#0', $DecPt, '000000'))"/>
<xsl:variable name="DecPl8" select="string(concat('#0', $DecPt, '00000000'))"/>

<xsl:variable name="DegreesSymbol" select="'&#0176;'"/>
<xsl:variable name="MinutesSymbol"><xsl:text>'</xsl:text></xsl:variable>
<xsl:variable name="SecondsSymbol" select="'&quot;'"/>

<xsl:variable name="fileExt" select="'htm'"/>
<xsl:variable name="IncludeBorders" select="'Yes'"/>

<xsl:key name="travDefnID-search" match="//JOBFile/FieldBook/TraverseDefinitionRecord" use="@ID"/>
<xsl:key name="ptName-search" match="//JOBFile/FieldBook/PointRecord" use="Name"/>

<!-- User variable definitions - Appropriate fields are displayed on the       -->
<!-- Survey Controller screen to allow the user to enter specific values       -->
<!-- which can then be used within the style sheet definition to control the   -->
<!-- output data.                                                              -->
<!--                                                                           -->
<!-- All user variables must be identified by a variable element definition    -->
<!-- named starting with 'userField' (case sensitive) followed by one or more  -->
<!-- characters uniquely identifying the user variable definition.             -->
<!--                                                                           -->
<!-- The text within the 'select' field for the user variable description      -->
<!-- references the actual user variable and uses the '|' character to         -->
<!-- separate the definition details into separate fields as follows:          -->
<!-- For all user variables the first field must be the name of the user       -->
<!-- variable itself (this is case sensitive) and the second field is the      -->
<!-- prompt that will appear on the Survey Controller screen.                  -->
<!-- The third field defines the variable type - there are four possible       -->
<!-- variable types: Double, Integer, String and StringMenu.  These variable   -->
<!-- type references are not case sensitive.                                   -->
<!-- The fields that follow the variable type change according to the type of  -->
<!-- variable as follow:                                                       -->
<!-- Double and Integer: Fourth field = optional minimum value                 -->
<!--                     Fifth field = optional maximum value                  -->
<!--   These minimum and maximum values are used by the Survey Controller for  -->
<!--   entry validation.                                                       -->
<!-- String: No further fields are needed or used.                             -->
<!-- StringMenu: Fourth field = number of menu items                           -->
<!--             Remaining fields are the actual menu items - the number of    -->
<!--             items provided must equal the specified number of menu items. -->
<!--                                                                           -->
<!-- The style sheet must also define the variable itself, named according to  -->
<!-- the definition.  The value within the 'select' field will be displayed in -->
<!-- the Survey Controller as the default value for the item.                  -->
<xsl:variable name="userField1" select="'DeltaTol|Highlight traverse deltas exceeding|double|0.0|1.0'"/>
<xsl:variable name="DeltaTol" select="0.020"/>


<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="product">
  <xsl:choose>
    <xsl:when test="JOBFile/@product"><xsl:value-of select="JOBFile/@product"/></xsl:when>
    <xsl:otherwise>Trimble Survey Controller</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="version">
  <xsl:choose>
    <xsl:when test="JOBFile/@productVersion"><xsl:value-of select="JOBFile/@productVersion"/></xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number(JOBFile/@version div 100, $DecPl2, 'Standard')"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <HTML>

  <TITLE>Traverse Deltas Report</TITLE>
  <H1>Traverse Deltas Report</H1>

  <!-- Set the font size for use in tables -->
  <STYLE TYPE="text/css">
    BODY, TABLE, TD
    {
      font-size:13px;
    }
  </STYLE>

  <HEAD>
  </HEAD>

  <BODY>
    <xsl:call-template name="StartTable"/>
      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Job Name'"/>
        <xsl:with-param name="Val" select="JOBFile/@jobName"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="concat($product, ' version')"/>
        <xsl:with-param name="Val" select="$version"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Distance units'"/>
        <xsl:with-param name="Val" select="$DistUnit"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Angle units'"/>
        <xsl:with-param name="Val" select="$AngleUnit"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Pressure units'"/>
        <xsl:with-param name="Val" select="$PressUnit"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Temperature units'"/>
        <xsl:with-param name="Val" select="$TempUnit"/>
      </xsl:call-template>
    <xsl:call-template name="EndTable"/>
    <xsl:call-template name="SeparatingLine"/>

    <!-- Select the FieldBook node to process -->
    <xsl:apply-templates select="JOBFile/FieldBook" />
    
  </BODY>
  </HTML>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">
<!-- Process the records under the FieldBook node in the order encountered -->
  <xsl:for-each select="*">
    <xsl:choose>
      <!-- Handle each TraverseClosureRecord record -->
      <xsl:when test="name(current()) = 'TraverseClosureRecord'">
        <xsl:apply-templates select="current()"/> 
      </xsl:when>

    </xsl:choose>
  </xsl:for-each>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** TraverseClosureRecord Handling **************** -->
<!-- **************************************************************** -->
<xsl:template match="TraverseClosureRecord">
  <!-- Get the traverse name from the associated TraverseDefinitionRecord -->
  <xsl:variable name="TravName">
    <xsl:for-each select="key('travDefnID-search', TraverseDefinitionID)">
      <xsl:value-of select="TraverseName"/>
    </xsl:for-each>
  </xsl:variable>
  
  <xsl:call-template name="StartTable"/>
    <CAPTION align="left"><xsl:value-of select="concat('Traverse Deltas: ', $TravName)"/></CAPTION>

    <!-- Now find each of the PointRecords following the TraverseClosureRecord -->
    <!-- that are TraverseAdjusted points -->
    <xsl:call-template name="TraverseAdjustedPoints"/> 
  <xsl:call-template name="EndTable"/>

</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Traverse Adjusted Point Handling *************** -->
<!-- **************************************************************** -->
<xsl:template name="TraverseAdjustedPoints">

  <xsl:if test="name(following-sibling::*[1]) = 'PointRecord' and 
                following-sibling::*[1]/Method = 'TraverseAdjusted'">
    <xsl:apply-templates select="following-sibling::*[1]"/>    
  </xsl:if>

</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord">

  <xsl:variable name="coordsStr">
    <xsl:for-each select="key('ptName-search', Name)">
      <xsl:if test="(Deleted = 'false') and ComputedGrid">
        <xsl:value-of select="concat(ComputedGrid/North, '|',
                                     ComputedGrid/East, '|',
                                     ComputedGrid/Elevation, '|')"/>
      </xsl:if>
    </xsl:for-each>
  </xsl:variable>

  <!-- Now extract the first set of original (unadjusted) coordinates -->
  <!-- encountered for the point.                                     -->
  <xsl:variable name="origNorth">
    <xsl:value-of select="substring-before($coordsStr, '|')"/>
  </xsl:variable>
  
  <xsl:variable name="coordsStr2">
    <xsl:value-of select="substring($coordsStr, string-length($origNorth) + 2)"/>
  </xsl:variable>

  <xsl:variable name="origEast">
    <xsl:value-of select="substring-before($coordsStr2, '|')"/>
  </xsl:variable>
  
  <xsl:variable name="coordsStr3">
    <xsl:value-of select="substring($coordsStr2, string-length($origEast) + 2)"/>
  </xsl:variable>
  
  <xsl:variable name="origElevation">
    <xsl:value-of select="substring-before($coordsStr3, '|')"/>
  </xsl:variable>
  
  <xsl:variable name="polarDeltaSq" select="((Grid/North - number($origNorth)) * (Grid/North - number($origNorth)) + 
                                             (Grid/East - number($origEast)) * (Grid/East - number($origEast))) *
                                            $DistConvFactor * $DistConvFactor"/>

  <xsl:call-template name="OutputSingleElementTableLine">
    <xsl:with-param name="Hdr" select="'Point'"/>
    <xsl:with-param name="Val" select="Name"/>
  </xsl:call-template>

  <xsl:call-template name="OutputSingleElementTableLine">
    <xsl:with-param name="Hdr">
      <xsl:choose>
        <xsl:when test="$NECoords = 'true'">&#0160;dNorth</xsl:when>
        <xsl:otherwise>&#0160;dEast</xsl:otherwise>
      </xsl:choose>
    </xsl:with-param>

    <xsl:with-param name="Val">
      <xsl:choose>
        <xsl:when test="$NECoords = 'true'">
          <xsl:value-of select="format-number((Grid/North - number($origNorth)) * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="format-number((Grid/East - number($origEast)) * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:with-param>

    <xsl:with-param name="HighlightVal">
      <xsl:choose>
        <xsl:when test="$polarDeltaSq > $DeltaTol * $DeltaTol">
          <xsl:value-of select="'Yes'"/>
        </xsl:when>
        <xsl:otherwise><xsl:value-of select="'No'"/></xsl:otherwise>
      </xsl:choose>
    </xsl:with-param>
  </xsl:call-template>

  <xsl:call-template name="OutputSingleElementTableLine">
    <xsl:with-param name="Hdr">
      <xsl:choose>
        <xsl:when test="$NECoords = 'true'">&#0160;dEast</xsl:when>
        <xsl:otherwise>&#0160;dNorth</xsl:otherwise>
      </xsl:choose>
    </xsl:with-param>

    <xsl:with-param name="Val">
      <xsl:choose>
        <xsl:when test="$NECoords = 'true'">
          <xsl:value-of select="format-number((Grid/East - number($origEast)) * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="format-number((Grid/North - number($origNorth)) * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:with-param>

    <xsl:with-param name="HighlightVal">
      <xsl:choose>
        <xsl:when test="$polarDeltaSq > $DeltaTol * $DeltaTol">
          <xsl:value-of select="'Yes'"/>
        </xsl:when>
        <xsl:otherwise><xsl:value-of select="'No'"/></xsl:otherwise>
      </xsl:choose>
    </xsl:with-param>
  </xsl:call-template>

  <xsl:if test="(Grid/Elevation != '') and ($origElevation != '')">
    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'&#0160;dElev'"/>
      <xsl:with-param name="Val" select="format-number((Grid/Elevation - number($origElevation)) * $DistConvFactor, $DecPl3, 'Standard')"/>
    </xsl:call-template>
  </xsl:if>
  
  <!-- Get the next Traverse Adjusted point if the next record is a Traverse Adjusted point -->
  <xsl:call-template name="TraverseAdjustedPoints"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <xsl:choose>
    <xsl:when test="$IncludeBorders != 'Yes'">  <!-- Only include separating lines -->
      <hr></hr>                                 <!-- if there are no table borders -->
    </xsl:when>
    <xsl:otherwise>
      <xsl:call-template name="BlankLine"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************ Output Table Line ********************* -->
<!-- **************************************************************** -->
<xsl:template name="OutputTableLine">
  <xsl:param name="Hdr1" select="''"/>
  <xsl:param name="Val1" select="''"/>
  <xsl:param name="Hdr2" select="''"/>
  <xsl:param name="Val2" select="''"/>
  <xsl:param name="Hdr3" select="''"/>
  <xsl:param name="Val3" select="''"/>
  <xsl:param name="Hdr4" select="''"/>
  <xsl:param name="Val4" select="''"/>
  <xsl:param name="Hdr5" select="''"/>
  <xsl:param name="Val5" select="''"/>

  <TR>
<!--  Possible alternative
  <xsl:choose>
    <xsl:when test="$Val1 = ''">
      <TH width="9%" align="left" colspan="2"><xsl:value-of select="$Hdr1"/></TH>
    </xsl:when>
    <xsl:otherwise>
      <TH width="9%" align="left"><xsl:value-of select="$Hdr1"/></TH>
      <TD width="11%" align="right"><xsl:value-of select="$Val1"/></TD>
    </xsl:otherwise>
  </xsl:choose>
-->
  <TH width="9%" align="left"><xsl:value-of select="$Hdr1"/></TH>
  <TD width="11%" align="right"><xsl:value-of select="$Val1"/></TD>
  <TH width="9%" align="left"><xsl:value-of select="$Hdr2"/></TH>
  <TD width="11%" align="right"><xsl:value-of select="$Val2"/></TD>
  <TH width="9%" align="left"><xsl:value-of select="$Hdr3"/></TH>
  <TD width="11%" align="right"><xsl:value-of select="$Val3"/></TD>
  <TH width="9%" align="left"><xsl:value-of select="$Hdr4"/></TH>
  <TD width="11%" align="right"><xsl:value-of select="$Val4"/></TD>
  <TH width="9%" align="left"><xsl:value-of select="$Hdr5"/></TH>
  <TD width="11%" align="right"><xsl:value-of select="$Val5"/></TD>
  </TR>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ************** Output Single Element Table Line **************** -->
<!-- **************************************************************** -->
<xsl:template name="OutputSingleElementTableLine">
  <xsl:param name="Hdr" select="''"/>
  <xsl:param name="Val" select="''"/>
  <xsl:param name="HighlightVal" select="'No'"/>

  <TR>
  <TH width="50%" align="left"><xsl:value-of select="$Hdr"/></TH>
  <xsl:choose>
    <xsl:when test="$HighlightVal != 'No'">
      <TD width="50%" align="right"><FONT color="red"><B><xsl:value-of select="$Val"/></B></FONT></TD>
    </xsl:when>
    <xsl:otherwise>
      <TD width="50%" align="right"><xsl:value-of select="$Val"/></TD>
    </xsl:otherwise>
  </xsl:choose>
  </TR>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************* Blank Line Output ************************ -->
<!-- **************************************************************** -->
<xsl:template name="BlankLine">
  <xsl:value-of select="string(' ')"/>
  <BR/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************* Start Table ************************** -->
<!-- **************************************************************** -->
<xsl:template name="StartTable">
  <xsl:choose>
    <xsl:when test="$IncludeBorders = 'Yes'">
      <xsl:value-of disable-output-escaping="yes" select="'&lt;TABLE BORDER=1 width=100% cellpadding=2 rules=cols&gt;'"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of disable-output-escaping="yes" select="'&lt;TABLE BORDER=0 width=100% cellpadding=2 rules=cols&gt;'"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************** End Table *************************** -->
<!-- **************************************************************** -->
<xsl:template name="EndTable">
  <xsl:value-of disable-output-escaping="yes" select="'&lt;/TABLE&gt;'"/>
</xsl:template>


</xsl:stylesheet>